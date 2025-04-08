import logging
import socket
import typing
from functools import lru_cache

import attr
try:
    import dns.query
    import dns.rdataclass
    import dns.rdatatype
    import dns.resolver
    import dns.zone
except ModuleNotFoundError:
    dns = None

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


def hosts_if_not_me(hosts: list) -> typing.List[Host]:
    _myhn = socket.gethostname()
    _log.debug('Resolving {}'.format(_myhn))
    for _hn in [oh for oh in hosts if oh != _myhn]:
        _log.debug('Resolving {}'.format(_hn))
        try:
            yield Host(_hn, gethostbyname(_hn))
        except socket.gaierror as e:
            _log.error(f'Error resolving {_hn}: {e}')


HOSTS = {
    'linux': {'phoenix', 'raspy2', 'raspy3', 'raspykey', 'plone-01', 'biglinux', 'octopi', 'pathfinder'},
    'mac': {'quark', 'bigmac', 'mini'},
}


def hosts_from_dns(dns_zone: typing.Optional[str], log: logging.Logger) -> dict:
    if dns_zone:
        try:
            soa_answer = dns.resolver.resolve(dns_zone, 'SOA')
            full_zone = dns.zone.from_xfr(dns.query.xfr(dns.resolver.resolve(soa_answer[0].mname, 'A')[0].address, dns_zone))
            all_hosts = {'linux': set(), 'mac': set()}
            for record_name, dns_record in full_zone.items():
                txt_rdata = dns_record.get_rdataset(dns.rdataclass.IN, dns.rdatatype.TXT)
                if txt_rdata:
                    for record_text in [s.decode('utf-8').lower() for t in txt_rdata for s in t.strings]:
                        if record_text in all_hosts.keys():
                            all_hosts[record_text].add(record_name.to_text().lower())
            return all_hosts
        except AttributeError:
            log.info('Using hardcoded hosts as requested')
    return HOSTS
