#!/usr/bin/env python3
import os
import re
import sys


def main(argv: list = sys.argv[1:]) -> int:
    # grep -v -e 'pool returned' -e '[Cc]ipher' -e /sbin/ip -e 'VERIFY OK' -e ifconfig_pool_set -e 'peer info' canne.log
    skip_regexp = re.compile(
        r'pool returned|[Cc]ipher|/sbin/ip|VERIFY OK|ifconfig_pool_set|peer info|Using [0-9]+ bit message hash|'
        r'library versions: OpenSSL|TUN/TAP device tun[0-9]+ opened|TCPv4_SERVER link'
    )
    for log_file in argv:
        lines = []
        uniques = dict()
        if not os.path.isfile(log_file):
            print(' * "{log_file}" not found *')
            continue
        with open(log_file, 'r') as f:
            lines = f.readlines()
        for line in lines:
            uniques[tuple(re.sub(r':[0-9]+', ':<port>', w) for w in line.split()[5:] if not re.search(skip_regexp, line))] = line
        print(''.join(sorted(uniques.values())))
    return 0


if __name__ == '__main__':
    sys.exit(main())
