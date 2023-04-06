#!/Volumes/MoviablesX/VMs/tools/bin/python
import argparse
import logging
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from subprocess import run, PIPE

try:
    import dns.query
    import dns.resolver
    import dns.zone
except ModuleNotFoundError:
    dns = None
try:
    from tools.libs.parse_args import LoggingArgumentParser
except Exception:
    from argparse import ArgumentParser as LoggingArgumentParser
from argparse import ArgumentError

APP_NAME = "BoT.All"
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
    def __init__(self, command, verbose: bool = False):
        self.command = command
        self.verbose = verbose

    def run_remote_command(self, host: str) -> (str, str, str, int):
        ssh_options = ['-o', 'StrictHostKeyChecking false', '-o', 'ConnectTimeout 5', '-o', 'BatchMode yes']
        if not self.verbose:
            ssh_options.append('-q')
        result = run(['ssh'] + ssh_options + [host, self.command], stdout=PIPE, stderr=PIPE, universal_newlines=True)
        return (host, CommandResult(result.stdout.rstrip('\n'), result.stderr.rstrip('\n'), result.returncode))


def parse_args(argv: list) -> argparse.Namespace:
    p = LoggingArgumentParser(APP_NAME)
    p.add_argument('command', help='Command to run (single string)')
    p.add_argument(
        '--dns-zone', '-D', default='canne', help='DNS zone to transfer to get hosts, empty to use hardcoded data'
    )
    p.add_argument('--linux', '-l', action='store_true', help='Only Linux hosts')
    p.add_argument('--mac', '-m', action='store_true', help='Only Mac hosts')
    p.add_argument('--extra', '-e', default=[], nargs='*', help='Extra hosts')
    p.add_argument('--with-errors', '-E', action='store_true', help='Also show error output')
    try:
        p.add_argument('--verbose', '-v', action='store_true')
        p.add_argument('--quiet', '-q', action='store_true')
    except ArgumentError:
        pass
    cfg = p.parse_args(argv)
    try:
        cfg.log.debug('Using LoggingArgumentParser')
    except AttributeError:
        cfg.log = logging.getLogger(APP_NAME)
        cfg.log.addHandler(logging.StreamHandler(sys.stdout))
        if cfg.verbose:
            cfg.log.setLevel(logging.DEBUG)
            print(f'Using ArgumentParser: {cfg.log}')
        elif cfg.quiet:
            cfg.log.setLevel(logging.ERROR)
        else:
            cfg.log.setLevel(logging.INFO)
    return cfg


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
        return HOSTS


def main(argv: list = sys.argv[1:]):
    cfg = parse_args(argv)
    cr = CommandRunner(cfg.command, verbose=cfg.with_errors)
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
            cfg.log.info(result[1].text(prefix=f'{result[0]}: '))


if __name__ == '__main__':
    sys.exit(main())
