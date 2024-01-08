#!/mnt/opt/nicola/tools/bin/python3
import attr
import argparse
import getpass
import json
import logging
import os
import subprocess
import sys
import typing

if os.path.abspath(os.path.dirname(os.path.dirname(__file__))) not in sys.path:
    sys.path.insert(1, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
from tools.libs.parse_args import LoggingArgumentParser
from tools.libs.total_block_config import config
from tools.libs.net_utils import ip_if_not_local

APP_NAME = 'LockDown'


def parse_args(argv: list, descr: str = 'Manage internet lockdown') -> argparse.Namespace:
    global log
    parser = LoggingArgumentParser(description=descr, app_name=APP_NAME)
    parser.add_argument('command', help='on or off', choices=('on', 'off'))
    parser.add_argument('--unsafe', action='store_true', help='Really run commands')
    cfg = parser.parse_args(argv)
    cfg_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    cfg.config = config[cfg.command]

    log = cfg.log
    return cfg


def user_if_not_me(user) -> typing.Optional[str]:
    if user != getpass.getuser():
        return user


def run(host_user, cmd, unsafe):
    user, host = host_user.split('@')
    if ip_if_not_local(host):
        full_cmd = ['ssh', host_user, cmd]
    elif user_if_not_me(user):
        full_cmd = ['sudo', '-u', user, cmd]
    else:
        full_cmd = ['bash', '-c', cmd]
    if unsafe:
        glue = '" "'
        log.debug(f'Running {glue.join(full_cmd)}')
        subprocess.run(full_cmd)
    else:
        full_cmd = '" "'.join(full_cmd)
        log.info(f'"{cmd}" on {host} (as {user}): "{full_cmd}"')


def is_valid(line: str) -> bool:
    return line[0] != '#' and ':' in line


def main(argv=sys.argv[1:]):
    cfg = parse_args(argv)
    cfg.log.info('Lock down %s initiated', cfg.command)
    for host_user, cmd in cfg.config:
        run(host_user, cmd, cfg.unsafe)
    return 0


if __name__ == '__main__':
    sys.exit(main())
