#!/mnt/opt/nicola/tools/bin/python3
import argparse
from datetime import datetime
import re
import sys


def parse_args(argv: list) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description='Squid logs alerter', formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    p.add_argument('--client-ips', nargs='+', default=['192.168.19.137'])
    p.add_argument('--log-file', default='/var/log/squid/access.log')
    p.add_argument('--whitelist-file', default='/etc/squid/whitelist.txt')
    return p.parse_args(argv)


def main(argv: list = sys.argv[1:]):
    cfg = parse_args(argv)
    with open(cfg.whitelist_file, 'r') as whitelists:
        whitelist_regex = re.compile('|'.join([l.strip() for l in whitelists.readlines() if l.strip()]))
    with open(cfg.log_file, 'r') as log:
        for line in log:
            if any([ip in line for ip in cfg.client_ips]):
                if '/200 ' in line and not re.search(whitelist_regex, line):
                    split_line = line.split()
                    pline = ' '.join([str(datetime.utcfromtimestamp(float(split_line[0])))] + split_line[1:])
                    print(pline.strip())


if __name__ == '__main__':
    sys.exit(main())
