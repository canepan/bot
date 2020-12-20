#!/Volumes/MoviablesX/VMs/tools/bin/python
import argparse
import os
import re
import stat
import subprocess
import sys

ORIG_MODE = stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
DEFAULTS = {
    'minecraft_ctl': {'launcher': '/Applications/Minecraft.app/Contents/MacOS/launcher', 'processes': ('java', 'minecraft')},
    'diablo3_ctl': {'launcher': '/Volumes/MoviablesX/Mac/Diablo III/Diablo III.app/Contents/MacOS/Diablo III', 'processes': ('Diablo III',)},
    'docker_ctl': {'launcher': '/Applications/Docker.app/Contents/MacOS/Docker', 'processes': ('Docker',)},
    'firefox_ctl': {'launcher': '/Applications/Firefox.app/Contents/MacOS/firefox', 'processes': ('firefox',), 'signal': '9'},
}


def parse_args(argv: list, prog_name: str = sys.argv[0]) -> argparse.Namespace:
    defaults = DEFAULTS[re.sub(r'\.py$', '', os.path.basename(prog_name))]
    p = argparse.ArgumentParser(
        description='App disabler', formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    p.add_argument('command', choices=('on', 'off', 'status'))
    p.add_argument('--launcher', '-l', default=defaults['launcher'])
    p.add_argument('--processes', '-p', nargs='+', default=defaults['processes'])
    p.add_argument('--kill-signal', '-k', type=int, default=defaults.get('signal', '15'))
    p.add_argument('--verbose', '-v', action='store_true')
    return p.parse_args(argv)


def list_instances(terms, verbose: bool = False) -> dict:
    ps_out = subprocess.check_output(['ps', 'auxwww'], stderr=subprocess.PIPE).decode('utf-8')
    pids = {}
    for line in ps_out.splitlines():
        if verbose:
            print('Looking for {} in {}'.format(terms, line))
        if all({t.lower() in line.lower() for t in terms}):
            pids[int(line.split()[1])] = line
    return pids


def kill_all_instances(terms, signal=15) -> None:
    for pid in list_instances(terms):
        os.kill(pid, signal)
        print('{} killed ({})'.format(pid, signal))


def main(argv: list = sys.argv[1:]) -> int:
    cfg = parse_args(argv)
    if cfg.command == 'on':
        os.chmod(cfg.launcher, ORIG_MODE)
    elif cfg.command == 'off':
        os.chmod(cfg.launcher, 0)
        kill_all_instances(cfg.processes, cfg.kill_signal)
    elif cfg.command == 'status':
        f_mode = os.stat(cfg.launcher).st_mode & 0o777
        pids = list_instances(cfg.processes, verbose=cfg.verbose)
        print('{}: {} ({}), {}\n{}'.format(
            cfg.launcher, 'active' if f_mode != 0 else 'disabled', oct(f_mode), 'running' if pids else 'not running', '\n  '.join(pids.values())
        ))
    else:
        print('Syntax:\n {} on|off|status\n({} provided)'.format(sys.argv[0], cfg.command))
    return 0


if __name__ == '__main__':
    sys.exit(main())
