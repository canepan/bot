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


@attr.s
class FirewallManager(object):
    rules: tuple = attr.ib()
    pretend = attr.ib(default=True)

    def allow(self):
        command = ['ssh', '-i', '/Users/nicola/.ssh/mt_remote', 'manage_internet@mt', f'/ip firewall address-list disable numbers={self.rules}']
        if self.pretend:
            return f'Would execute {command}'
        return subprocess.check_output(command, stderr=subprocess.PIPE).decode('utf-8')

    def deny(self):
        command = ['ssh', '-i', '/Users/nicola/.ssh/mt_remote', 'manage_internet@mt', f'/ip firewall address-list enable numbers={self.rules}']
        if self.pretend:
            return f'Would execute {command}'
        return subprocess.check_output(command, stderr=subprocess.PIPE).decode('utf-8')

    def status(self):
        output = subprocess.check_output(
            ['ssh', 'admin@mt', f'/ip firewall address-list print'], stderr=subprocess.PIPE
        ).decode('utf-8')
        return self.findrules(output)

    def findrules(self, output):
        rules_lines = []
        found = False
        for line in output.splitlines():
            fields = line.split()
            if found:
                found = False
                rules_lines.append(line)
            try:
                if fields and int((fields[0])) in self.rules:
                    found = True
                    rules_lines.append(line)
            except ValueError:
                pass
        return '\n'.join(rules_lines)


@attr.s
class ProcessManager(object):
    terms: typing.List[typing.Pattern] = attr.ib()
    log: logging.Logger = attr.ib()

    def list_instances(self, verbose: bool = False) -> dict:
        ps_out = subprocess.check_output(['ps', 'auxwww'], stderr=subprocess.PIPE).decode('utf-8')
        pids = {}
        for line in ps_out.splitlines():
            if any({re.search(t, line) for t in self.terms}):
                pids[int(line.split()[1])] = line
        return pids

    def kill_all_instances(self, signal: int, pretend: bool) -> None:
        for pid, cmdline in self.list_instances(self.terms).items():
            self.log.debug('Found {}: signaling {}'.format(cmdline, signal))
            if not pretend:
                os.kill(pid, signal)
            self.log.info('{} killed ({})'.format(pid, signal))


TFileNames = typing.Union[str, typing.List[str]]

@attr.s
class PermsManager(object):
    executable: TFileNames = attr.ib()
    pretend: bool = attr.ib(True)

    def change_perms(self, perms: int):
        try:
            if self.pretend:
                self.executable.lower()
                print('Would change {} to {}'.format(self.executable, perms))
            else:
                os.chmod(self.executable, perms)
        except (AttributeError, TypeError):
            if self.pretend:
                for ex in self.executable:
                    print('Would change {} to {}'.format(ex, perms))
            else:
                for ex_path in self.executable:
                    try:
                        os.chmod(ex_path, perms)
                    except FileNotFoundError as fnfe:
                        print(fnfe)

    def enable(self):
        self.change_perms(ORIG_MODE)

    def disable(self):
        self.change_perms(0)

    def stat_files(self, file_names: TFileNames):
        try:
            f_mode = os.stat(file_names).st_mode & 0o777
            return {file_names: f_mode}
        except TypeError:
            # return {file_name: os.stat(file_name).st_mode & 0o777 for file_name in file_names}
            result = {}
            for file_name in file_names:
                try:
                    result[file_name] = os.stat(file_name).st_mode & 0o777
                except FileNotFoundError as fnfe:
                    print(fnfe)
            return result


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
class ProxyManager(Executor):
    proxy_commands: dict = attr.ib(dict())
    pretend: bool = attr.ib(True)

    def allow(self):
        results = []
        for command in self.proxy_commands['enable']:
            command = ['ssh', '-t', '-i', '/Users/nicola/.ssh/id_rsa', 'phoenix', command + ' || true']
            results.append(self.exec(command))
        return '\n'.join(results)

    def deny(self):
        results = []
        for command in self.proxy_commands['disable']:
            command = ['ssh', '-t', '-i', '/Users/nicola/.ssh/id_rsa', 'phoenix', command + ' || true']
            results.append(self.exec(command))
        return '\n'.join(results)


def main(argv: list = sys.argv[1:], prog_name: str = sys.argv[0]) -> int:
    cfg = parse_args(argv, prog_name)
    if not cfg:
        return 1
    if cfg.firewall:
        firewall = FirewallManager(cfg.firewall, cfg.pretend)
    proc_mgr = ProcessManager(cfg.processes, cfg.log)
    perms_mgr = PermsManager(cfg.launcher, cfg.pretend)
    proxy_mgr = ProxyManager(cfg.proxy, cfg.pretend)
    if cfg.command == 'on':
        if cfg.firewall:
            print(firewall.allow())
        print(proxy_mgr.allow())
        perms_mgr.enable()
    elif cfg.command == 'off':
        perms_mgr.disable()
        proc_mgr.kill_all_instances(cfg.kill_signal, cfg.pretend)
        print(proxy_mgr.deny())
        if cfg.firewall:
            print(firewall.deny())
    elif cfg.command == 'status':
        f_modes = perms_mgr.stat_files(cfg.launcher)
        pids = proc_mgr.list_instances(verbose=cfg.verbose)
        if cfg.verbose:
            print('\n  '.join(pids.values()))
        for launcher, f_mode in f_modes.items():
            print(
                '{}: {} ({}), {}'.format(
                    launcher, 'active' if f_mode != 0 else 'disabled', oct(f_mode), 'running' if pids else 'not running'
                )
            )
        if cfg.firewall:
            print(firewall.status())
    else:
        print('Syntax:\n {} on|off|status\n({} provided)'.format(sys.argv[0], cfg.command))
    return 0


if __name__ == '__main__':
    sys.exit(main())
