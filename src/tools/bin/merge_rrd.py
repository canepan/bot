#!/usr/bin/env python

"""
Simple script to merge multiple RRD files together.

Accepts any number of RRD file names as arguments.  Produces an "rrdtool dump"
style file on stdout.  The last RRD file should have a slot for every possible
record in the resulting merged RRD.

Run something like:
$ python simple-merge-rrd.py filea.rrd fileb.rrd filec.rrd | \
    rrdtool restore /dev/stdin merged.rrd

Credits:
https://gist.github.com/arantius/2166343
https://gist.github.com/m3rlinux/e0ebe1fba39789f27209577cf4a08685
"""

import re
import subprocess
import sys


def main():
  rrd_data = {}
  rrds = sys.argv[1:]
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


if __name__ == '__main__':
  main()
