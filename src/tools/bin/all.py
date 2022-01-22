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
    p = argparse.ArgumentParser()
    p.add_argument('command', help='Command to run (single string)')
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
    return _myhn.split('.')[0].lower() != hostname


def extend_if_not_me(hosts, hosts_to_add: list) -> list:
    for host in hosts_to_add:
        if not_me(host):
            hosts.append(host)
    return hosts


def main(argv: list = sys.argv[1:]):
    cfg = parse_args(argv)
    cr = CommandRunner(cfg.command)
    hosts = list(cfg.extra)
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
        if cfg.with_errors or result[1].returncode == 0:
            print(result[1].text(prefix=f'{result[0]}: '))


if __name__ == '__main__':
    sys.exit(main())
