#!/bin/sh
# Taken from http://rosettacode.org/wiki/Multiline_shebang#Python
"true" '''\'
[ -x "${HOME}/Documents/venv/nwn/bin/python" ] && exec "${HOME}/Documents/venv/nwn/bin/python" "$0" "$@"
exec /usr/bin/env python3 "$0" "$@"
exit 127
'''
__doc__ = 'Run a command by first mounting local or remote image files on Mac'
import argparse
import logging
import os
import subprocess
import sys
import textwrap
import time

import attr


@attr.s
class RunFromImage(object):
    remote_hosts = ['quark', 'foo_rsync', 'www.nicolacanepa.net']
    pretend: bool = attr.ib(default=True)
    verbose: bool = attr.ib(default=True)
    offline: bool = attr.ib(default=False)
    _timeout: int = attr.ib(default=2)

    def __attrs_post_init__(self) -> None:
        self._indent = 0
        self._unison_cmd = ['unison', '-sshargs', f'-o "ConnectTimeout {self._timeout}"']
        self.log = logging.getLogger('canepa.nwn')
        self.log.addHandler(logging.StreamHandler(sys.stdout))
        if self.verbose:
            self.log.setLevel(logging.DEBUG)
        else:
            self.log.setLevel(logging.INFO)

    def indented(self, func_name, *args, **kwargs):
        self._indent += 1
        result = func_name(*args, **kwargs)
        self._indent -= 1
        return result

    def _indent_first(self, *args):
        return (textwrap.indent(args[0], self._indent * '  '),) + args[1:]

    def debug(self, *args, **kwargs):
        self.log.debug(*self._indent_first(*args), **kwargs)

    def info(self, *args, **kwargs):
        self.log.info(*self._indent_first(*args), **kwargs)

    def error(self, *args, **kwargs):
        self.log.error(*self._indent_first(*args), **kwargs)

    def _exec(self, cmd: list) -> subprocess.CompletedProcess:
        self.info('Running %s', ' '.join(cmd))
        if self.pretend:
            return subprocess.CompletedProcess(cmd, 0)
        self.debug('Exec: %s', ' '.join(['"{}"'.format(c) for c in cmd]))
        cprocess = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.info(cprocess.stdout.decode('utf-8'))
        if cprocess.returncode != 0:
            self.error(cprocess.stderr.decode('utf-8'))
        return cprocess

    def _mkdir(self, _dir: str) -> int:
        self.debug('Create dir %s', _dir)
        if not (self.pretend or os.path.isdir(_dir)):
            try:
                os.makedirs(_dir)
            except OSError as e:
                self.error('Unable to create dir %s: %s', _dir, e)
                return 1
        return 0

    def _rmdir(self, _dir: str) -> int:
        self.debug('Remove dir %s', _dir)
        if not self.pretend and os.path.isdir(_dir):
            try:
                os.rmdir(_dir)
            except OSError as e:
                self.error('Unable to remove dir %s: %s', _dir, e)
                return 1
        return 0

    def _mount_local(self, _dmg: str, _dir: str) -> int:
        self.info('Mounting %s to %s', _dmg, _dir)
        _err = self.indented(self._mkdir, _dir)
        cmd = ['hdiutil', 'mount']
        cmd.extend([_dmg, '-mountpoint', _dir])
        self.debug('Mount %s to %s', _dmg, _dir)
        _err += self.indented(self._exec, cmd).returncode
        return _err

    def _umount_local(self, _dir: str) -> int:
        _err = self._umount(_dir)
        _err += self._rmdir(_dir)
        return _err

    def _umount(self, _dir: str) -> int:
        self.info('Unmounting %s', _dir)
        cmd = ['hdiutil', 'eject']
        if self.verbose:
            cmd.append('-verbose')
        cmd.append(_dir)
        self.debug('Umount %s', _dir)
        return self.indented(self._exec, cmd).returncode

    def _non_failing_sync(self, _dir: str):
        if self._exec(self._unison_cmd + ['-testserver', 'nwn']).returncode == 0:
            self._exec(self._unison_cmd + ['-batch', 'nwn'])

    def _mount_via_ssh(self, _dir: str) -> int:
        if self.offline:
            self.info('Skip mounting %s remotely (offline)', _dir)
            return 0
        self._non_failing_sync(_dir)
        self.info('Mounting %s remotely', _dir)
        for _host in self.remote_hosts:
            self.debug('Select remote host')
            cmd = ['ssh', '-o', f'ConnectTimeout {self._timeout}', '-q', _host, 'hostname']
            if self.indented(self._exec, cmd).returncode != 0:
                continue
            self.remote_hosts = [_host]
            relative_dir = os.path.relpath(_dir, os.environ['HOME'])
            self.debug('SSH mount %s:%s to %s', _host, relative_dir, _dir)
            _err = self.indented(self._mkdir, _dir)
            _err += self.indented(self._exec, ['sshfs', f'{_host}:{relative_dir}', _dir]).returncode
            return _err
        return 1

    def _umount_ssh(self, _dir: str) -> int:
        return self._umount(_dir)

    def _ln(self, orig, dest) -> int:
        orig = os.path.relpath(orig, os.path.dirname(dest))
        self.debug('Symlink %s to %s', orig, dest)
        if not self.pretend:
            try:
                os.symlink(orig, dest)
            except OSError as e:
                self.error('Unable to symlink %s to %s: %s', orig, dest, e)
                return 1
        return 0

    def _rm(self, fname) -> int:
        self.debug('Remove %s', fname)
        if not self.pretend:
            try:
                os.remove(fname)
            except OSError as e:
                self.error('Unable to remove %s: %s', fname, e)
                return 1
        return 0

    def on(self) -> int:
        _err = self._mount_local(self.data_dmg, self.data_link)
        # if os.path.islink(data_link):
        #     _err += self._rm(data_link)
        # _err += self._ln(f'{data_dir}/Neverwinter Nights', data_link)
        _err += self._mount_via_ssh(f'{self.data_link}/{self.saves}')
        _err += self._mount_local(self.bin_dmg, self.bin_dir)
        _err += self._exec([self.main_exe]).returncode
        return _err

    def off(self) -> int:
        _err = self._umount_ssh(f'{self.data_link}/{self.saves}')
        _err += self._umount_local(self.bin_dir)
        umount_err = self._umount_local(self.data_link)
        if umount_err == 0:
            if os.path.islink(self.data_link):
                self.info('Removing link %s', self.data_link)
                _err += self._rm(self.data_link)
        else:
            _err += umount_err
        return _err


class NWN(RunFromImage):
    def __init__(self, *args, **kwargs):
        # self.data_dmg = os.path.expanduser('~/Documents/Nicola/NWNSaveGames.sparsebundle')
        documents = os.path.expanduser('~/Documents')
        my_documents = f'{documents}/Nicola'
        self.data_dmg = f'{my_documents}/NWNConfig.sparseimage'
        self.data_dir = f'{my_documents}/MacData'
        self.data_link = f'{documents}/Neverwinter Nights'
        self.saves = 'saves'
        self.bin_dmg = f'{my_documents}/NicolaMac.dmg'
        self.bin_dir = f'{my_documents}/Mac'
        self.main_exe = f'{self.bin_dir}/Neverwinter Nights Enhanced Edition/bin/macos/nwmain.app/Contents/MacOS/nwmain'
        super().__init__(*args, **kwargs)


class Torment(RunFromImage):
    def __init__(self, *args, **kwargs):
        documents = os.path.expanduser('~/Documents')
        my_documents = f'{documents}/Nicola'
        self.data_dmg = os.path.expanduser('~/Documents/Nicola/TConfig.sparseimage')
        self.data_dir = os.path.expanduser('~/Documents/Nicola/MacData')
        self.data_link = os.path.expanduser('~/Documents/Planescape Torment - Enhanced Edition')
        self.saves = 'save'
        self.bin_dmg = os.path.expanduser('~/Documents/Nicola/NicolaT.dmg')
        self.bin_dir = os.path.expanduser('~/Documents/Nicola/Mac')
        self.main_exe = (f'{self.bin_dir}/Planescape Torment - Enhanced Edition.app/Contents/MacOS/'
                         'Planescape Torment - Enhanced Edition')
        super().__init__(*args, **kwargs)


def parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['on', 'off'], default='on', nargs='?')
    g = parser.add_mutually_exclusive_group()
    g.add_argument('--nwn', '-N', action='store_false', help='Default: on')
    g.add_argument('--torment', '-T', action='store_true')
    parser.add_argument('--pretend', '-p', action='store_true')
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--skip-unmount', '-s', action='store_true')
    parser.add_argument('--offline', '-o', action='store_true')
    return parser.parse_args(argv)


def main(argv: list = sys.argv[1:]):
    cfg = parse_args(argv)
    if cfg.torment:
        play = Torment(verbose=cfg.verbose, pretend=cfg.pretend, offline=cfg.offline)
    else:
        play = NWN(verbose=cfg.verbose, pretend=cfg.pretend, offline=cfg.offline)

    if cfg.command == 'off':
        return play.off()
    elif cfg.command == 'on':
        _err = play.on()
        if not cfg.pretend and not cfg.skip_unmount:
            time.sleep(3)
        if not cfg.skip_unmount:
            _err += play.off()
        return _err


if __name__ == '__main__':
    main()
