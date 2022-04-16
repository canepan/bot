#!/Volumes/MoviablesX/VMs/tools/bin/python
import argparse
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from subprocess import run, PIPE

import dns.query
import dns.resolver
import dns.zone
from tools.libs.parse_args import LoggingArgumentParser

HOSTS = {
    'linux': {'phoenix', 'raspy2', 'raspy3', 'raspykey', 'plone-01', 'biglinux', 'octopi', 'pathfinder'},
    'mac': {'quark', 'bigmac', 'mini'},
}


class CommandResult(object):
    def __init__(self, stdout: str, stderr: str, returncode: int):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode

    def text(self, prefix: str = '') -> str:
        return_lines = [f'{prefix}{line}' for line in self.stdout.splitlines()]
        prefix = f'{prefix}(err{f": {self.returncode}" if self.returncode else ""}) '
        return_lines.extend([f'{prefix}{line}' for line in self.stderr.splitlines()])
        return '\n'.join(return_lines)


class CommandRunner(object):
    def __init__(self, command):
        self.command = command

    def run_remote_command(self, host: str) -> (str, str, str, int):
        # print(' '.join(['ssh', '-q', '-o StrictHostKeyChecking false', '-o ConnectTimeout 5', host, self.command]))
        result = run(['ssh', '-q', '-o StrictHostKeyChecking false', '-o ConnectTimeout 5', host, self.command], stdout=PIPE, stderr=PIPE, universal_newlines=True)
        return (host, CommandResult(result.stdout.rstrip('\n'), result.stderr.rstrip('\n'), result.returncode))


def parse_args(argv: list) -> argparse.Namespace:
    p = LoggingArgumentParser()
    p.add_argument('command', help='Command to run (single string)')
    p.add_argument(
        '--dns-zone', '-D', default='canne', help='DNS zone to transfer to get hosts, empty to use hardcoded data'
    )
    p.add_argument('--linux', '-l', action='store_true', help='Only Linux hosts')
    p.add_argument('--mac', '-m', action='store_true', help='Only Mac hosts')
    p.add_argument('--extra', '-e', default=[], nargs='*', help='Extra hosts')
    p.add_argument('--with-errors', '-E', action='store_true', help='Also show error output')
    return p.parse_args(argv)


@lru_cache(maxsize=1)
def gethostname() -> str:
    return socket.gethostname()


def not_me(hostname: str) -> bool:
    _myhn = gethostname()
    return _myhn.split('.')[0].lower() != hostname.lower()


def extend_if_not_me(hosts, hosts_to_add: list) -> list:
    for host in hosts_to_add:
        if not_me(host):
            hosts.append(host)
    return hosts


def hosts_from_dns(dns_zone) -> dict:
    all_hosts = {'linux': set(), 'mac': set()}
    soa_answer = dns.resolver.resolve(dns_zone, 'SOA')
    full_zone = dns.zone.from_xfr(dns.query.xfr(dns.resolver.resolve(soa_answer[0].mname, 'A')[0].address, dns_zone))
    for record_name, dns_record in full_zone.items():
        txt_rdata = dns_record.get_rdataset(dns.rdataclass.IN, dns.rdatatype.TXT)
        if txt_rdata:
            for record_text in [s.decode('utf-8').lower() for t in txt_rdata for s in t.strings]:
                if record_text in all_hosts.keys():
                    all_hosts[record_text].add(record_name.to_text())
    return all_hosts


def main(argv: list = sys.argv[1:]):
    cfg = parse_args(argv)
    cr = CommandRunner(cfg.command)
    if cfg.dns_zone:
        all_hosts_dict = hosts_from_dns(cfg.dns_zone)
    else:
        cfg.log.info('Using hardcoded hosts as requested')
        all_hosts_dict = HOSTS
    hosts = list(cfg.extra)
    if cfg.linux:
        extend_if_not_me(hosts, all_hosts_dict['linux'])
    elif cfg.mac:
        extend_if_not_me(hosts, all_hosts_dict['mac'])
    else:
        for htype, hosts_list in all_hosts_dict.items():
            extend_if_not_me(hosts, hosts_list)
    with ThreadPoolExecutor(16) as tpool:
        results = tpool.map(cr.run_remote_command, hosts, timeout=5)
    for result in results:
        if cfg.with_errors or result[1].returncode == 0:
            print(result[1].text(prefix=f'{result[0]}: '))


if __name__ == '__main__':
    sys.exit(main())
