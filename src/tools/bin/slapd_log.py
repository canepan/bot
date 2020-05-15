#!/mnt/opt/nicola/tools/bin/python3
import argparse
import json
import sys
from collections import defaultdict
from signal import signal, SIGINT


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('input_file', default=sys.stdin, type=argparse.FileType('r'), nargs='?')
    return parser.parse_args()


def handler(signal_received, frame):
    slapd_threads = frame.f_locals.get('slapd_threads')
    if slapd_threads:
        print(json.dumps(slapd_threads, indent=2))
    else:
        print('Specify an input file, or provide the log via standard input')
        sys.exit(2)
    sys.exit(1)


def empty_dict() -> dict:
    return {'err_0': [], 'errors': [], 'other': [], 'search': []}


def parse_result(parts: list):
    flow_dict = {}
    if parts[2] == 'err=0':
        if 'nentries=' in parts[3]:
            flow_dict['nresults'] = int(parts[3].split('=')[1])
        else:
            flow_dict['err_0'] = [' '.join(parts)]
    else:
        flow_dict['errors'] = [' '.join(parts)]
    return flow_dict


def main(argv=sys.argv[1:]):
    cfg = parse_args(argv)
    signal(SIGINT, handler)
    slapd_threads = defaultdict(empty_dict)
    for line in cfg.input_file:
        parts = line.split()
        if parts[1] == '<=':
            continue
        flow_dict = slapd_threads[' '.join(parts[0:2])]
#            flow_dict = slapd_threads[parts[0]]
        if parts[3] == 'ACCEPT':
            flow_dict['src_ip'] = parts[5].split('=')[1]
            dst_ip_port = parts[6].strip('()')
            flow_dict['ds_tip'], flow_dict['dst_port'] = dst_ip_port.split(':')
        elif parts[3] == 'RESULT':
            res = parse_result(parts[3:])
            flow_dict['errors'].extend(res.get('errors', []))
            flow_dict['err_0'].extend(res.get('err_0', []))
        elif parts[3] == 'SEARCH' and parts[4] == 'RESULT':
            res = parse_result(parts[4:])
            flow_dict['errors'].extend(res.get('errors', []))
            flow_dict['err_0'].extend(res.get('err_0', []))
        elif parts[3] == 'SRCH':
            flow_dict['search'].append(' '.join(parts[4:]))
        elif parts[3] == 'BIND':
            flow_dict['who'] = parts[4]
        elif parts[2] == 'mdb_equality_candidates:' or parts[3] == 'closed':
            pass
        else:
            flow_dict['other'].append(' '.join(parts[2:]))
    print(json.dumps(slapd_threads, indent=2))


if __name__ == '__main__':
    sys.exit(main())
