#!/Volumes/MoviablesX/VMs/tools/bin/python
import argparse
import attr
import logging
import os
import re
import stat
import subprocess
import sys

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
        'signal': '9',
    },
    'diablo3_ctl': {
        'launcher': '/Volumes/MoviablesX/Mac/Diablo III/Diablo III.app/Contents/MacOS/Diablo III',
        'processes': ('Diablo III',),
    },
    'docker_ctl': {'launcher': '/Applications/Docker.app/Contents/MacOS/Docker', 'processes': ('Docker',)},
    'firefox_ctl': {
        'launcher': '/Applications/Firefox.app/Contents/MacOS/firefox',
        'processes': ('[Ff]irefox',),
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
    rules = attr.ib()
    pretend = attr.ib(default=True)

    def allow(self):
        command = ['ssh', 'admin@mt', f'/ip firewall address-list disable numbers={self.rules}']
        if self.pretend:
            return f'Would execute {command}'
        return subprocess.check_output(command, stderr=subprocess.PIPE).decode('utf-8')

    def deny(self):
        command = ['ssh', 'admin@mt', f'/ip firewall address-list enable numbers={self.rules}']
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


def list_instances(terms, verbose: bool = False) -> dict:
    ps_out = subprocess.check_output(['ps', 'auxwww'], stderr=subprocess.PIPE).decode('utf-8')
    pids = {}
    for line in ps_out.splitlines():
        if any({re.search(t, line) for t in terms}):
            pids[int(line.split()[1])] = line
    return pids


def kill_all_instances(terms: list, signal: int, log: logging.Logger, pretend: bool) -> None:
    for pid, cmdline in list_instances(terms).items():
        log.debug('Found {}: signaling {}'.format(cmdline, signal))
        if not pretend:
            os.kill(pid, signal)
        log.info('{} killed ({})'.format(pid, signal))


def change_perms(executable, perms: int, pretend: bool):
    try:
        if pretend:
            executable.lower()
            print('Would change {} to {}'.format(executable, perms))
        else:
            os.chmod(executable, perms)
    except (AttributeError, TypeError):
        if pretend:
            for ex in executable:
                print('Would change {} to {}'.format(ex, perms))
        else:
            for ex_path in executable:
                try:
                    os.chmod(ex_path, perms)
                except FileNotFoundError as fnfe:
                    print(fnfe)


def enable(executable, pretend: bool):
    change_perms(executable, ORIG_MODE, pretend)


def disable(executable, pretend: bool):
    change_perms(executable, 0, pretend)


def stat_files(file_names):
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


def main(argv: list = sys.argv[1:], prog_name: str = sys.argv[0]) -> int:
    cfg = parse_args(argv, prog_name)
    if not cfg:
        return 1
    if cfg.firewall:
        firewall = FirewallManager(cfg.firewall, cfg.pretend)
    if cfg.command == 'on':
        if cfg.firewall:
            print(firewall.allow())
        enable(cfg.launcher, cfg.pretend)
    elif cfg.command == 'off':
        disable(cfg.launcher, cfg.pretend)
        kill_all_instances(cfg.processes, cfg.kill_signal, cfg.log, cfg.pretend)
        if cfg.firewall:
            print(firewall.deny())
    elif cfg.command == 'status':
        f_modes = stat_files(cfg.launcher)
        pids = list_instances(cfg.processes, verbose=cfg.verbose)
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
