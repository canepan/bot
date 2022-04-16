#!/mnt/opt/nicola/tools/bin/python3
import os
import socket
import subprocess
import sys

import attr

from ..libs.stools_defaults import host_if_not_me, parse_args
from .sdiff import show_diffs


def main(argv: list = sys.argv[1:]):
    if argv[0] == '-diff':
        extra_args = {'filenames': {'nargs': '+'}}
        command = show_diffs
    elif argv[0] == '-exe':
        extra_args = {'command': {}}
    elif argv[0] == '-syn':
        extra_args = {'filenames', {'nargs': '+'}}
    else:
        args.log.error('Please specify either -diff or -exe as the first argument')
        return 1
    args = parse_args(argv[1:], extra_args)
    _other_hosts = host_if_not_me(args.hosts)

    return command(args.filenames, _other_hosts, args)
    for _host in _other_hosts:
        for _fn in args.filenames:
            try:
                result = subprocess.check_output(
                    'ssh {0} "cat \'{1}\'" | {2} "{1}" - ; exit 0'.format(_host.hostname, _fn, args.diff),
                    stderr=subprocess.STDOUT,
                    shell=True,
                )
                if result.decode():
                    args.log.info('Diff between local and {}:{}'.format(_host.hostname, _fn))
                    args.log.info(result.decode())
                else:
                    args.log.info('{} is the same on {}'.format(_fn, _host.hostname))
            except subprocess.CalledProcessError as e:
                args.log.error(e.output.decode())
                args.log.debug('Exit code: {}'.format(e.returncode))
            except Exception as e:
                args.log.error(e)
        return 0


if __name__ == '__main__':
    sys.exit(main())
