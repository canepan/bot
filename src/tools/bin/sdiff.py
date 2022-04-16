#!/mnt/opt/nicola/tools/bin/python
import argparse
import os
import socket
import subprocess
import sys

from ..libs.stools_defaults import HOSTS
from ..libs.parse_args import LoggingArgumentParser
from ..libs.text_utils import CompareContents, file_content

APP_NAME = 'SSHDiff'


def parse_args(argv: list):
    parser = LoggingArgumentParser(
        description='Checks the difference between local and remote files with the sane name',
        app_name=APP_NAME,
    )
    parser.add_argument('--hosts', '-H', nargs='+', default=HOSTS)
    parser.add_argument('--diff', '-d', default='diff -buB', help='Command (with params) to use for diff')
    parser.add_argument('filename', nargs='+')
    return parser.parse_args(argv)


def show_diffs(filenames, hostnames, args: argparse.Namespace):
    for _fn in filenames:
        for _hn in hostnames:
            args.log.debug('Resolving {}'.format(_hn))
            try:
                _ip = socket.gethostbyname(_hn)
                remote_content = subprocess.check_output(
                    ['ssh', _hn, f'cat "{_fn}"'],
                    stderr=subprocess.STDOUT,
                ).decode()
                local_content = file_content(_fn)
                if remote_content.strip() != local_content.strip():
                    diff = CompareContents(
                        local_content,
                        remote_content,
                        old_file_name=_fn,
                        new_file_name=f'{_hn}:{_fn}',
                    )
                    args.log.info('Diff between local and %s:%s\n%s', _hn, _fn, diff)
                else:
                    args.log.info('%s is the same on %s', _fn, _hn)
            except subprocess.CalledProcessError as e:
                args.log.error(e.output.decode())
                args.log.debug('Exit code: %s', e.returncode)
            except socket.gaierror as e:
                args.log.error('Error resolving %s: %s', _hn, e)
            except Exception as e:
                args.log.error(e)


def main(argv: list = sys.argv[1:]):
    args = parse_args(argv)

    _myhn = socket.gethostname()
    args.log.debug('Resolving {}'.format(_myhn))
    _myip = socket.gethostbyname(_myhn)
    _other_hosts = [_hn for _hn in args.hosts if _hn != _myhn]
    show_diffs(args.filename, _other_hosts, args)


if __name__ == '__main__':
    sys.exit(main())
