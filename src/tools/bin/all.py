#!/Volumes/MoviablesX/VMs/tools/bin/python
import argparse
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from subprocess import run, PIPE

HOSTS = {
    'linux': ['phoenix', 'raspy2', 'raspy3', 'raspykey', 'plone-01', 'biglinux', 'octopi', 'pathfinder'],
    'mac': ['quark', 'bigmac', 'mini'],
}


class CommandRunner(object):
    def __init__(self, command):
        self.command = command

    def run_remote_command(self, host: str) -> (str, str, str, int):
        # print(' '.join(['ssh', '-q', '-o StrictHostKeyChecking false', '-o ConnectTimeout 5', host, self.command]))
        result = run(['ssh', '-q', '-o StrictHostKeyChecking false', '-o ConnectTimeout 5', host, self.command], stdout=PIPE, stderr=PIPE, universal_newlines=True)
        return (host, result.stdout.rstrip('\n'), result.stderr.rstrip('\n'), result.returncode)


def parse_args(argv: list) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument('command', help='Command to run (single string)')
    p.add_argument('--linux', '-l', action='store_true', help='Only Linux hosts')
    p.add_argument('--mac', '-m', action='store_true', help='Only Mac hosts')
    p.add_argument('--with-errors', '-E', action='store_true', help='Also show error output')
    return p.parse_args(argv)


@lru_cache(maxsize=1)
def gethostname() -> str:
    return socket.gethostname()


def not_me(hostname: str) -> bool:
    _myhn = gethostname()
    return _myhn.split('.')[0].lower() != hostname


def extend_if_not_me(hosts, hosts_to_add: list) -> list:
    for host in hosts_to_add:
        if not_me(host):
            hosts.append(host)
    return hosts


def main(argv: list = sys.argv[1:]):
    cfg = parse_args(argv)
    cr = CommandRunner(cfg.command)
    hosts = list()
    if cfg.linux:
        extend_if_not_me(hosts, HOSTS['linux'])
    elif cfg.mac:
        extend_if_not_me(hosts, HOSTS['mac'])
    else:
        for htype, hosts_list in HOSTS.items():
            extend_if_not_me(hosts, hosts_list)
    with ThreadPoolExecutor(16) as tpool:
        results = tpool.map(cr.run_remote_command, hosts, timeout=5)
    for result in results:
        if cfg.with_errors or result[3] == 0:
            text = '\n'.join([r for r in result[1:3] if r])
            print(f'{result[0]}: {text}{"" if result[3] == 0 else f"({result[3]})"}')


if __name__ == '__main__':
    sys.exit(main())
