#!/mnt/opt/nicola/tools/bin/python
import argparse
import os
import socket
import subprocess
import sys

from ..libs.stools_defaults import HOSTS
from ..libs.parse_args import LoggingArgumentParser

APP_NAME = 'SSHDiff'


def parse_args(argv):
    parser = LoggingArgumentParser(
        description='Checks the difference between local and remote files with the sane name',
        app_name=APP_NAME,
    )
    parser.add_argument('--hosts', '-H', nargs='+', default=HOSTS)
    parser.add_argument('--diff', '-d', default='diff -buB', help='Command (with params) to use for diff')
    parser.add_argument('filename', nargs='+')
    return parser.parse_args(argv)


def main(argv: list = sys.argv[1:]):
    args = parse_args(argv)
    _other_hosts = args.hosts

    _myhn = socket.gethostname()
    args.log.debug('Resolving {}'.format(_myhn))
    _myip = socket.gethostbyname(_myhn)
    for _fn in args.filename:
        for _hn in _other_hosts:
            if _hn != _myhn:
                args.log.debug('Resolving {}'.format(_hn))
                try:
                    _ip = socket.gethostbyname(_hn)
                    if _ip != _myip:
                        result = subprocess.check_output(
                            'ssh {0} "cat \'{1}\'" | {2} "{1}" - ; ' 'exit 0'.format(_hn, _fn, args.diff),
                            stderr=subprocess.STDOUT,
                            shell=True,
                        )
                        if result.decode():
                            args.log.info('Diff between local and %s:%s\n%s', _hn, _fn, result.decode())
                        else:
                            args.log.info('%s is the same on %s', _fn, _hn)
                except subprocess.CalledProcessError as e:
                    args.log.error(e.output.decode())
                    args.log.debug('Exit code: %s', e.returncode)
                except socket.gaierror as e:
                    args.log.error('Error resolving %s: %s', _hn, e)
                except Exception as e:
                    args.log.error(e)


if __name__ == '__main__':
    sys.exit(main())
