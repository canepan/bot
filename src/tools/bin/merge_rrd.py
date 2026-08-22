#!/usr/bin/env python3

"""
Simple script to merge multiple RRD files together.

Accepts any number of RRD file names as arguments.  Produces an "rrdtool dump"
style file on stdout.  The last RRD file should have a slot for every possible
record in the resulting merged RRD.

Arguments ending in ".rrd" are used as-is.  Any other argument is treated as a
speedtest-cli JSON log (one JSON object per line, with "timestamp", "upload",
"download" and "ping" fields).  Log files are converted to a temporary RRD
with the same structure as the last .rrd argument, fed through
"rrdtool update" so consolidation is computed by rrdtool itself, and then
merged like any other RRD.

Later arguments take precedence where they have non-NaN data, so to fill a
gap in ispeed.rrd from the log run:

$ python3 merge-rrd.py speedtest.log ispeed.rrd | \
    rrdtool restore /dev/stdin merged.rrd

Credits:
https://gist.github.com/arantius/2166343
https://gist.github.com/m3rlinux/e0ebe1fba39789f27209577cf4a08685
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

# Force a locale with '.' as decimal separator for all child processes:
# rrdtool info/dump/create otherwise format and parse numbers using the
# host locale (e.g. "5,0000000000e-01"), breaking round-tripping.
os.environ['LC_ALL'] = 'C'

# The temp RRD's heartbeat is relaxed by this factor so that update
# intervals with a little jitter (e.g. 601s vs a 600s heartbeat) are not
# discarded as unknown.  This only affects the backfill conversion: the
# merged output keeps the heartbeat of the template (last) RRD.
HEARTBEAT_TOLERANCE = 2

# Maps RRD datasource names to speedtest.log JSON keys.
FIELD_MAP = {
    'uploadspeed': 'upload',
    'downloadspeed': 'download',
    'ping': 'ping',
}


def rrd_info(rrdname):
  """Parse `rrdtool info` into step, last_update, DS list and RRA list."""
  out = subprocess.getoutput("rrdtool info {}".format(rrdname))
  info = dict(re.findall(r'^(\S+) = "?([^"\n]*)"?$', out, re.M))
  step = int(info['step'])
  last_update = int(info['last_update'])

  ds = []  # (name, type, heartbeat) in index order
  for name in re.findall(r'^ds\[(\w+)\]\.index', out, re.M):
    ds.append((name,
               info['ds[{}].type'.format(name)],
               info['ds[{}].minimal_heartbeat'.format(name)]))

  rras = []  # (cf, xff, pdp_per_row, rows)
  i = 0
  while 'rra[{}].cf'.format(i) in info:
    rras.append((info['rra[{}].cf'.format(i)],
                 info['rra[{}].xff'.format(i)],
                 int(info['rra[{}].pdp_per_row'.format(i)]),
                 int(info['rra[{}].rows'.format(i)])))
    i += 1
  return step, last_update, ds, rras


def parse_log(logname, start, end):
  """Yield sorted (epoch, {field: value}) tuples from a speedtest JSON log."""
  entries = {}
  with open(logname) as f:
    for line in f:
      line = line.strip()
      if not line.startswith('{'):
        continue
      try:
        d = json.loads(line)
      except json.JSONDecodeError:
        continue
      try:
        ts = datetime.strptime(d['timestamp'][:19], '%Y-%m-%dT%H:%M:%S')
      except (KeyError, ValueError):
        continue
      t = int(ts.replace(tzinfo=timezone.utc).timestamp())
      if start <= t <= end:
        entries[t] = d
  return sorted(entries.items())


def log_to_rrd(logname, ref_rrd):
  """Convert a speedtest log to a temp RRD shaped like ref_rrd.

  Returns the temp RRD path (caller must remove it).
  """
  step, last_update, ds, rras = rrd_info(ref_rrd)

  # Only feed entries that can land in the reference RRD's RRA windows.
  span = max(pdp * rows for _cf, _xff, pdp, rows in rras) * step
  updates = parse_log(logname, last_update - span, last_update)
  if not updates:
    sys.exit('{}: no usable log entries within the time range of {}'.format(
        logname, ref_rrd))

  fd, tmp = tempfile.mkstemp(suffix='.rrd')
  os.close(fd)
  cmd = ['rrdtool', 'create', tmp,
         '--start', str(updates[0][0] - 1), '--step', str(step)]
  cmd += ['DS:{}:{}:{}:U:U'.format(name, dstype, int(hb) * HEARTBEAT_TOLERANCE)
          for name, dstype, hb in ds]
  cmd += ['RRA:{}:{}:{}:{}'.format(cf, xff, pdp, rows)
          for cf, xff, pdp, rows in rras]
  subprocess.run(cmd, check=True)

  def value(entry, name):
    key = FIELD_MAP.get(name, name)
    v = entry.get(key)
    return str(v) if v is not None else 'U'

  args = ['{}:{}'.format(t, ':'.join(value(e, name) for name, _t, _h in ds))
          for t, e in updates]
  for i in range(0, len(args), 100):
    subprocess.run(['rrdtool', 'update', tmp] + args[i:i + 100], check=True)

  print('{}: fed {} log entries ({} .. {}) into temp RRD'.format(
      logname, len(updates),
      datetime.fromtimestamp(updates[0][0], timezone.utc),
      datetime.fromtimestamp(updates[-1][0], timezone.utc)), file=sys.stderr)
  return tmp


def main():
  sources = sys.argv[1:]
  if not sources:
    sys.exit(__doc__)

  ref_rrds = [s for s in sources if s.endswith('.rrd')]
  if not ref_rrds:
    sys.exit('At least one .rrd file is required as merge template.')
  ref_rrd = ref_rrds[-1]

  temp_files = []
  rrds = []
  for src in sources:
    if src.endswith('.rrd'):
      rrds.append(src)
    else:
      tmp = log_to_rrd(src, ref_rrd)
      temp_files.append(tmp)
      rrds.append(tmp)

  try:
    rrd_data = {}
    last_rrd = len(rrds) - 1

    for i, rrdname in enumerate(rrds):
      p = subprocess.getoutput("rrdtool dump {}".format(rrdname))
      for line in p.split("\n"):
        m = re.search(r'<cf>(.*)</cf>', line)
        if m:
          cf = m.group(1)
        m = re.search(r'<pdp_per_row>(.*)</pdp_per_row>', line)
        if m:
          pdp = m.group(1)

        m = re.search(r' / (\d+) --> (.*)', line)
        if m:
          k = cf + pdp
          rrd_data.setdefault(k, {})
          if ('NaN' not in m.group(2)) or (
              m.group(1) not in rrd_data[k]):
            rrd_data[k][m.group(1)] = line
          line = rrd_data[k][m.group(1)]

        if i == last_rrd:
          print(line.rstrip())
  finally:
    for tmp in temp_files:
      os.unlink(tmp)


if __name__ == '__main__':
  main()
