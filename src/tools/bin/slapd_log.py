#!/mnt/opt/nicola/tools/bin/python3
import argparse
import json
import sys
from collections import defaultdict
from signal import signal, SIGINT


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('input_file', default=sys.stdin, type=argparse.FileType('r'), nargs='?')
    parser.add_argument('--json', '-j', action='store_true', help='Output a JSON')
    return parser.parse_args()


def handler(signal_received, frame):
    slapd_threads = frame.f_locals.get('slapd_threads')
    if slapd_threads:
        print(slapd_threads)
    else:
        print('Specify an input file, or provide the log via standard input')
        sys.exit(2)
    sys.exit(1)


def empty_dict() -> dict:
    return {'err_0': [], 'errors': [], 'other': [], 'search': []}


class LdapLogFlow(dict):
    def __init__(self, *args, **kwargs):
        kwargs['err_0'] = []
        kwargs['errors'] = []
        kwargs['other'] = []
        kwargs['mod'] = []
        kwargs['search'] = []
        self.last_op = None
        super(LdapLogFlow, self).__init__(*args, **kwargs)

    def parse_result(self, parts: list):
        if parts[2] == 'err=0':
            if 'nentries=' in parts[3]:
                self['search'].append(int(parts[3].split('=')[1]))
            else:
                self['err_0'].append(' '.join(parts))
        else:
            self['errors'].append(' '.join(parts))
            if self.last_op in ('mod', 'search'):
                self[self.last_op].append(' '.join(parts))

    def parse_parts(self, parts: list):
        if parts[3] == 'ACCEPT':
            self['src_ip'] = parts[5].split('=')[1]
            dst_ip_port = parts[6].strip('()')
            self['dst_ip'], self['dst_port'] = dst_ip_port.split('=')[1].split(':')
        elif parts[3] == 'RESULT':
            self.parse_result(parts[3:])
        elif parts[3] == 'SEARCH' and parts[4] == 'RESULT':
            self.parse_result(parts[4:])
        elif parts[3] == 'MOD':
            self['mod'].append(' '.join(parts[4:]))
            self.last_op = 'mod'
        elif parts[3] == 'SRCH':
            self['search'].append(' '.join(parts[4:]))
            self.last_op = 'search'
        elif parts[3] == 'BIND':
            self['who'] = parts[4]
            self.last_op = 'who'
        elif parts[3] == 'UNBIND':
            pass
        elif parts[2] == 'mdb_equality_candidates:' or parts[3] == 'closed':
            pass
        else:
            self['other'].append(' '.join(parts[2:]))

    def __bool__(self):
        return any(self.values())


class LdapLog(object):
    def __init__(self, show_json=False):
        self.data = defaultdict(LdapLogFlow)
        self.show_json = show_json

    def parse_line(self, line):
        parts = line.split()
        if parts[1] == '<=':
            return
        flow_dict = self.data[' '.join(parts[0:2])]
#        flow_dict = self.data[parts[0]]
        flow_dict.parse_parts(parts)

    def __str__(self):
        if self.show_json:
            return json.dumps(self.data, indent=2)
        lines = []
        for k, data_flow in self.data.items():
            if data_flow:
                v = {i: j for i, j in data_flow.items() if j}
                lines.append(f'{k}: {json.dumps(v, indent=2)}')
        return '\n'.join(lines)


def main(argv=sys.argv[1:]):
    cfg = parse_args(argv)
    signal(SIGINT, handler)
    slapd_threads = LdapLog(show_json=cfg.json)
    for line in cfg.input_file:
        slapd_threads.parse_line(line)
    print(slapd_threads)


if __name__ == '__main__':
    sys.exit(main())
