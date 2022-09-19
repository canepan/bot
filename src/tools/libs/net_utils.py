import logging
import socket
import typing
from functools import lru_cache

import attr

APP_NAME = 'canepan.tools'
_log = logging.getLogger(APP_NAME)


@attr.s
class Host(object):
    hostname = attr.ib(type=str)
    ip = attr.ib(type=str)


@lru_cache(maxsize=5)
def gethostbyname(hn: str) -> str:
    return socket.gethostbyname(hn)


def ip_if_not_local(host: str) -> typing.Optional[str]:
    """ return the resolved IP if it's not the local IP """
    _ip = gethostbyname(host)
    my_host = socket.gethostname()
    if my_host != host and _ip != gethostbyname(my_host):
        return _ip


def host_if_not_me(hosts: list) -> typing.List[Host]:
    _myhn = socket.gethostname()
    _log.debug('Resolving {}'.format(_myhn))
    for _hn in [oh for oh in hosts if oh != _myhn]:
        _log.debug('Resolving {}'.format(_hn))
        try:
            yield Host(_hn, gethostbyname(_hn))
        except socket.gaierror as e:
            _log.error(f'Error resolving {_hn}: {e}')
