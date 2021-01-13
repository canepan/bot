#!/mnt/opt/nicola/tools/bin/python3
import argparse
import os
import re
import sys
import tempfile
from datetime import datetime


def parse_args(argv: list) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description='Squid logs alerter', formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    p.add_argument('--client-ips', nargs='+', default=['192.168.19.137'])
    p.add_argument('--log-file', default='/var/log/squid/access.log')
    p.add_argument('--whitelist-file', default='/etc/squid/whitelist.txt')
    p.add_argument('--breaches-file', default='/tmp/proxy_breaches.txt')
    return p.parse_args(argv)


def main(argv: list = sys.argv[1:]):
    cfg = parse_args(argv)
    curr_breaches = []
    with open(cfg.whitelist_file, 'r') as whitelists:
        whitelist_regex = re.compile('|'.join([l.strip() for l in whitelists.readlines() if l.strip()]))
    with open(cfg.log_file, 'r') as log:
        for line in log:
            if any([ip in line for ip in cfg.client_ips]):
                if '/200 ' in line and not line.startswith('#') and not re.search(whitelist_regex, line):
                    split_line = line.split()
                    # 6: site_url
                    fqdn = re.search(r'(http://)?\([a-zA-Z\.0-9]]*\)[:/]', split_line[6])
                    # pline = ' '.join([str(datetime.utcfromtimestamp(float(split_line[0])))] + split_line[1:])
                    # print(pline.strip())
                    curr_breaches.append('{} {}'.format(datetime.utcfromtimestamp(float(split_line[0])), split_line[6]))
                    # print(fqdn)
    if os.path.exists(cfg.breaches_file):
        with open(cfg.breaches_file, 'r') as breaches:
            prev_breaches = breaches.read()
    else:
        prev_breaches = ''
    breaches = '\n'.join(curr_breaches)
    if prev_breaches != breaches:
        print(breaches)
        with open(cfg.breaches_file, 'w') as f:
            f.write(breaches)


if __name__ == '__main__':
    sys.exit(main())
