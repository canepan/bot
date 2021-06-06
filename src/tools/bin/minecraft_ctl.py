#!/Volumes/MoviablesX/VMs/tools/bin/python
import argparse
import attr
import json
import logging
import os
import re
import stat
import subprocess
import sys
import typing
from abc import ABC, abstractmethod

ORIG_MODE = stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
DEFAULTS = {
    'minecraft_ctl': {
        'launcher': [
            '/Applications/Minecraft.app/Contents/MacOS/launcher',
            '/Applications/Lunar Client.app/Contents/MacOS/Lunar Client',
            '/Applications/Badlion Client.app/Contents/MacOS/Badlion Client',
        ],
        'processes': ('java.*mojang', '[Mm]inecraft[^_]', '[Ll]unar', 'Badlion'),
        'firewall': (10, 11),
        'proxy': {
            'enable': ['/usr/local/bin/manage_discord.py enable && /etc/init.d/e2guardian restart'],
            'disable': ['/usr/local/bin/manage_discord.py disable && /etc/init.d/e2guardian restart'],
            'status': [],
        },
        'signal': '9',
    },
    'diablo3_ctl': {
        'launcher': '/Volumes/MoviablesX/Mac/Diablo III/Diablo III.app/Contents/MacOS/Diablo III',
        'processes': ('Diablo III',),
    },
    'docker_ctl': {'launcher': '/Applications/Docker.app/Contents/MacOS/Docker', 'processes': ('Docker',)},
    'firefox_ctl': {
        'launcher': '/Applications/Firefox.app/Contents/MacOS/firefox',
        'processes': (r'Firefox\.app.*firefox',),
        'signal': '9',
    },
    'torbrowser_ctl': {
        'launcher': '/Applications/Tor Browser.app/Contents/MacOS/firefox',
        'processes': ('Tor.*Browser.*[Ff]irefox',),
        'signal': '9',
    },
}


def parse_args(argv: list, prog_name: str = sys.argv[0]) -> argparse.Namespace:
    defaults = DEFAULTS.get(re.sub(r'\.py$', '', os.path.basename(prog_name)))
    if not defaults:
        print('Please, run this as one of {}'.format(', '.join(DEFAULTS.keys())))
        return None
    p = argparse.ArgumentParser(description='App disabler', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('command', choices=('on', 'off', 'status'))
    p.add_argument('--launcher', '-l', default=defaults['launcher'])
    p.add_argument('--processes', '-p', nargs='+', default=defaults['processes'])
    p.add_argument('--kill-signal', '-k', type=int, default=defaults.get('signal', '15'))
    p.add_argument('--firewall', '-f', type=list, default=defaults.get('firewall', ()))
    p.add_argument('--proxy', '-x', type=json.loads, default=defaults.get('proxy', {'enable': [], 'disable': []}))
    p.add_argument('--pretend', '-P', action='store_true')
    p.add_argument('--quiet', '-q', action='store_true')
    p.add_argument('--verbose', '-v', action='store_true')
    cfg = p.parse_args(argv)
    cfg.log = logging.getLogger(prog_name)
    if cfg.quiet:
        cfg.log.addHandler(logging.NullHandler())
    else:
        cfg.log.addHandler(logging.StreamHandler())
        cfg.log.setLevel('INFO')
    if cfg.verbose:
        cfg.log.setLevel('DEBUG')
    return cfg


class AllowDenyManager(ABC):
    @abstractmethod
    def allow(self):
        pass

    @abstractmethod
    def deny(self):
        pass

    @abstractmethod
    def status(self):
        pass


@attr.s
class FirewallManager(AllowDenyManager):
    rules: tuple = attr.ib()
    log: logging.Logger = attr.ib()
    pretend = attr.ib(default=True)

    def allow(self):
        command = [
            'ssh',
            '-i',
            '/Users/nicola/.ssh/mt_remote',
            'manage_internet@mt',
            f'/ip firewall address-list disable numbers={self.rules}',
        ]
        if self.pretend:
            return f'Would execute {command}'
        return subprocess.check_output(command, stderr=subprocess.PIPE).decode('utf-8')

    def deny(self):
        command = [
            'ssh',
            '-i',
            '/Users/nicola/.ssh/mt_remote',
            'manage_internet@mt',
            f'/ip firewall address-list enable numbers={self.rules}',
        ]
        if self.pretend:
            return f'Would execute {command}'
        return subprocess.check_output(command, stderr=subprocess.PIPE).decode('utf-8')

    def status(self):
        output = subprocess.check_output(
            [
                'ssh',
                '-i',
                '/Users/nicola/.ssh/mt_remote',
                'manage_internet@mt',
                f'/ip firewall address-list print from={",".join([str(i) for i in self.rules])}',
            ],
            stderr=subprocess.PIPE,
        ).decode('utf-8')
        return output


@attr.s
class ProcessManager(AllowDenyManager):
    terms: typing.List[typing.Pattern] = attr.ib()
    log: logging.Logger = attr.ib()
    signal: int = attr.ib(default=15)
    pretend: bool = attr.ib(default=True)

    def status(self) -> dict:
        ps_out = subprocess.check_output(['ps', 'auxwww'], stderr=subprocess.PIPE).decode('utf-8')
        pids = {}
        for line in ps_out.splitlines():
            if any({re.search(t, line) for t in self.terms}):
                pids[int(line.split()[1])] = line
        self.log.info('{} {}'.format(self.terms, 'running' if pids else 'not running'))
        self.log.debug('\n  '.join(pids.values()))
        return pids

    def allow(self) -> None:
        pass

    def deny(self) -> None:
        for pid, cmdline in self.status().items():
            self.log.debug('Found {}: signaling {}'.format(cmdline, self.signal))
            if not self.pretend:
                os.kill(pid, self.signal)
            self.log.info('{} killed ({})'.format(pid, self.signal))


TFileNames = typing.Union[str, typing.List[str]]


@attr.s
class PermsManager(AllowDenyManager):
    executable: TFileNames = attr.ib()
    log: logging.Logger = attr.ib()
    pretend: bool = attr.ib(True)

    def change_perms(self, perms: int):
        executable = self.executable
        try:
            executable.lower()
            executable = [self.executable]
        except (AttributeError, TypeError):
            pass
        if self.pretend:
            for ex_path in executable:
                self.log.error('Would change {} to {}'.format(ex_path, perms))
        else:
            for ex_path in executable:
                try:
                    os.chmod(ex_path, perms)
                except FileNotFoundError as fnfe:
                    self.log.error(fnfe)

    def allow(self):
        self.change_perms(ORIG_MODE)

    def deny(self):
        self.change_perms(0)

    def status(self):
        try:
            f_mode = os.stat(self.executable).st_mode & 0o777
            f_modes = {self.executable: f_mode}
        except TypeError:
            f_modes = {}
            for file_name in self.executable:
                try:
                    f_modes[file_name] = os.stat(file_name).st_mode & 0o777
                except FileNotFoundError as fnfe:
                    self.log.error(f'{file_name} not found: {fnfe}')
        for launcher, f_mode in f_modes.items():
            self.log.debug('{}: {} ({}), '.format(launcher, 'active' if f_mode != 0 else 'disabled', oct(f_mode)))


@attr.s
class Executor(object):
    pretend: bool = attr.ib(True)

    def exec(self, *args, **kwargs) -> str:
        if 'stderr' not in kwargs:
            kwargs['stderr'] = subprocess.PIPE
        if self.pretend:
            return f'Would execute {args} {kwargs}'
        return subprocess.check_output(*args, **kwargs).decode('utf-8')


@attr.s
class ProxyManager(Executor, AllowDenyManager):
    log: logging.Logger = attr.ib()
    proxy_commands: dict = attr.ib(dict())
    pretend: bool = attr.ib(True)

    def allow(self):
        results = []
        for command in self.proxy_commands.get('enable', []):
            command = ['ssh', '-t', '-i', '/Users/nicola/.ssh/id_rsa', 'phoenix', command + ' || true']
            results.append(self.exec(command))
        return '\n'.join(results)

    def deny(self):
        results = []
        for command in self.proxy_commands.get('disable', []):
            command = ['ssh', '-t', '-i', '/Users/nicola/.ssh/id_rsa', 'phoenix', command + ' || true']
            results.append(self.exec(command))
        return '\n'.join(results)

    def status(self):
        results = []
        for command in self.proxy_commands.get('status', []):
            command = ['ssh', '-t', '-i', '/Users/nicola/.ssh/id_rsa', 'phoenix', command + ' || true']
            results.append(self.exec(command))
        return '\n'.join(results)


def main(argv: list = sys.argv[1:], prog_name: str = sys.argv[0]) -> int:
    cfg = parse_args(argv, prog_name)
    if not cfg:
        return 1
    managers = [
        PermsManager(cfg.launcher, pretend=cfg.pretend, log=cfg.log),
        ProcessManager(cfg.processes, log=cfg.log, signal=cfg.kill_signal, pretend=cfg.pretend),
        ProxyManager(proxy_commands=cfg.proxy, pretend=cfg.pretend, log=cfg.log),
    ]
    if cfg.firewall:
        managers.append(FirewallManager(cfg.firewall, pretend=cfg.pretend, log=cfg.log))
    for manager in managers:
        if cfg.command == 'on':
            output = manager.allow()
        elif cfg.command == 'off':
            output = manager.deny()
        elif cfg.command == 'status':
            output = manager.status()
        else:
            cfg.log.error('Syntax:\n {} on|off|status\n({} provided)'.format(sys.argv[0], cfg.command))
            return 1
        if output:
            cfg.log.info(output)
    return 0


if __name__ == '__main__':
    sys.exit(main())
