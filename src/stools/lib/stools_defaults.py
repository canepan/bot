import argparse
import logging
import socket
import sys

import attr


APP_NAME = 'canepan.stools'
HOSTS = ['phoenix', 'raspy2', 'raspy3']
_log = logging.getLogger(APP_NAME)


@attr.s
class Host(object):
    hostname = attr.ib(type=str)
    ip = attr.ib(type=str)


def parse_args(argv=None, descr='Sync local to remote files with the same name') -> argparse.Namespace:
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(
        description=descr,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('--diff', '-d', default='diff -buB', help='Command (with params) to use for diff')
    parser.add_argument('--hosts', '-H', nargs='+', default=HOSTS)
    parser.add_argument('filenames', nargs='+')
    g = parser.add_mutually_exclusive_group()
    g.add_argument('-q', '--quiet', action='store_true')
    g.add_argument('-v', '--verbose', action='store_true')
    cfg = parser.parse_args(argv)
    cfg.log = logging.getLogger(APP_NAME)
    if cfg.verbose:
        cfg.log.setLevel('DEBUG')
        cfg.log.addHandler(logging.StreamHandler())
    elif cfg.quiet:
        cfg.log.setLevel('ERROR')
    return cfg


def host_if_not_me(hosts: list) -> Host:
    _myhn = socket.gethostname()
    _log.debug('Resolving {}'.format(_myhn))
    _myip = socket.gethostbyname(_myhn)
    for _hn in [oh for oh in hosts if oh != _myhn]:
        _log.debug('Resolving {}'.format(_hn))
        try:
            _ip = socket.gethostbyname(_hn)
            if _ip != _myip:
                yield Host(_hn, _ip)
        except socket.gaierror as e:
                print('Error resolving {}: {}'.format(_hn, e))
