#!/mnt/opt/nicola/tools/bin/python3
import attr
import argparse
import json
import logging
import os
import subprocess
import sys

if os.path.abspath(os.path.dirname(os.path.dirname(__file__))) not in sys.path:
    sys.path.insert(1, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
from libs.parse_args import LoggingArgumentParser
from libs.stools_defaults import host_if_not_me

APP_NAME = 'LockDown'


def parse_args(argv: list, descr: str = 'Create e2g configuration') -> argparse.Namespace:
    global log
    parser = LoggingArgumentParser(description=descr, app_name=APP_NAME)
    parser.add_argument('command', help='on or off', choices=('on', 'off'))
    parser.add_argument('--unsafe', action='store_true', help='Really write/rename files')
    cfg =  parser.parse_args(argv)
    cfg_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    cfg.config = os.path.join(cfg_dir, f'total_block_{cfg.command}.cfg')

    log = cfg.log
    return cfg


def run(host_user, cmd, unsafe):
    user, host = host_user.split('@')
    if unsafe:
        subprocess.run(['ssh', host_user, cmd])
    else:
        log.info(f'"{cmd}" on {host} (as {user})')


def is_valid(line: str) -> bool:
    return line[0] != '#' and ':' in line


def main(argv=sys.argv[1:]):
    cfg = parse_args(argv)
    cfg.log.info('Lock down %s initiated', cfg.command)
    with open(cfg.config, 'r') as f:
        for line in [valid_line.strip() for valid line in f if is_valid(valid_line)]:
            host_user, cmd = line.split(':')
            run(host_user, cmd, cfg.unsafe)
    return 0


if __name__ == '__main__':
    sys.exit(main())
