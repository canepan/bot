#!/mnt/opt/nicola/tools/bin/python3
import os
import socket
import subprocess
import sys

import attr

from ..libs.stools_defaults import hosts_if_not_me, parse_args


def main(argv: list = sys.argv[1:]):
    args = parse_args(argv)
    _other_hosts = args.hosts

    for _host in hosts_if_not_me(args.hosts):
        for _fn in args.filenames:
            try:
                result = subprocess.check_output(
                    'ssh {0} "cat \'{1}\'" | {2} "{1}" - ; ' 'exit 0'.format(_host.hostname, _fn, args.diff),
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
