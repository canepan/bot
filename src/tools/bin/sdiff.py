#!/usr/bin/env python3
import argparse
import os
import socket
import subprocess
import sys

from ..lib.defaults import HOSTS


def debug(*text):
    if _debug:
        print(*text)


if __name__ == '__main__':
    _debug = os.environ.get('DEBUG', False) is not False
    #_other_hosts = os.environ.get('OTHER_HOSTS', 'raspy raspy2').split()
    parser = argparse.ArgumentParser(
        description='Checks the difference between local and remote files with the sane name',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('--hosts', '-H', nargs='+', default=hosts_defaults)
    parser.add_argument('--diff', '-d', default='diff -buB', help='Command (with params) to use for diff')
    parser.add_argument('filename', nargs='+')
    args = parser.parse_args()
    _other_hosts = args.hosts

    _myhn = socket.gethostname()
    debug('Resolving {}'.format(_myhn))
    _myip = socket.gethostbyname(_myhn)
    for _fn in args.filename:
        for _hn in _other_hosts:
            if _hn != _myhn:
                debug('Resolving {}'.format(_hn))
                try:
                    _ip = socket.gethostbyname(_hn)
                    if _ip != _myip:
                        result = subprocess.check_output(
                            'ssh {0} "cat \'{1}\'" | {2} "{1}" - ; '
                            'exit 0'.format(_hn, _fn, args.diff), stderr=subprocess.STDOUT, shell=True)
                        if result.decode():
                            print('Diff between local and {}:{}'.format(_hn, _fn))
                            print(result.decode())
                        else:
                            print('{} is the same on {}'.format(_fn, _hn))
                except subprocess.CalledProcessError as e:
                    print(e.output.decode())
                    debug('Exit code: {}'.format(e.returncode))
                except socket.gaierror as e:
                    print('Error resolving {}: {}'.format(_hn, e))
                except Exception as e:
                    print(e)

