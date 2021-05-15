#!/usr/bin/env python3
import argparse
import logging
import os
import subprocess
import sys
import textwrap
import time


class NWN(object):
    def _defaults(self) -> None:
        self.remote_hosts = ['quark', 'foo_rsync', 'www.nicolacanepa.net']
        self._BASE_DIR = os.path.expanduser('~/Documents')
        self._BASE_DATA = '{BASE_DIR}/Nicola'
        self._DATA_DMG = '{BASE_DATA}/NWNConfig.sparseimage'
        self._data_dir = '{BASE_DATA}/MacData'
        self._data_link = '{BASE_DIR}/Neverwinter Nights'
        self._bin_dmg = '{BASE_DATA}/NicolaMac.dmg'
        self._bin_dir = '{BASE_DATA}/Mac'
        self._main_exe = '{bin_dir}/Neverwinter Nights Enhanced Edition/bin/macos/nwmain.app/Contents/MacOS/nwmain'

    def __init__(self, pretend: bool = True, verbose: bool = True) -> None:
        self.unsafe = not pretend
        self.verbose = verbose
        self._indent = 0
        self.log = logging.getLogger('canepa.nwn')
        self.log.addHandler(logging.StreamHandler(sys.stdout))
        if self.verbose:
            self.log.setLevel(logging.DEBUG)
        self._data_dmg = None
        self._data_dir = None
        self._data_link = None
        self._bin_dmg = None
        self._bin_dir = None
        self._main_exe = None
        self._defaults()

    @property
    def BASE_DIR(self):
        return os.path.expanduser(self._BASE_DIR)

    @property
    def BASE_DATA(self):
        return self._BASE_DATA.format(BASE_DIR=self.BASE_DIR)

    @property
    def DATA_DMG(self):
        return self._DATA_DMG.format(BASE_DATA=self.BASE_DATA)

    @property
    def data_dir(self):
        return self._data_dir.format(BASE_DATA=self.BASE_DATA)

    @property
    def data_link(self):
        return self._data_link.format(BASE_DIR=self.BASE_DIR)

    @property
    def bin_dmg(self):
        return self._bin_dmg.format(BASE_DATA=self.BASE_DATA)

    @property
    def main_exe(self):
        return self._main_exe.format(bin_dir=self.bin_dir)

    @property
    def bin_dir(self):
        return self._bin_dir.format(BASE_DATA=self.BASE_DATA)

    @property
    def data_dmg(self) -> str:
        import inspect
        print(f'Running {inspect.getframeinfo(inspect.currentframe())[2]}')
        if self._data_dmg is None:
            self._data_dmg = self.DATA_DMG.format(BASE_DIR=self.BASE_DIR, BASE_DATA=self.BASE_DATA)
        return self._data_dmg

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
        self.debug('Exec: %s', ' '.join(['"{}"'.format(c) for c in cmd]))
        if self.unsafe:
            cprocess = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.info(cprocess.stdout.decode('utf-8'))
            if cprocess.returncode != 0:
                self.error(cprocess.stderr.decode('utf-8'))
            return cprocess
        return subprocess.CompletedProcess(cmd, 0)

    def _mkdir(self, _dir: str) -> int:
        self.debug('Create dir %s', _dir)
        if self.unsafe and not os.path.isdir(_dir):
            try:
                os.makedirs(_dir)
            except OSError as e:
                self.error('Unable to create dir %s: %s', _dir, e)
                return 1
        return 0

    def _rmdir(self, _dir: str) -> int:
        self.debug('Remove dir %s', _dir)
        if self.unsafe and os.path.isdir(_dir):
            try:
                os.rmdir(_dir)
            except OSError as e:
                self.error('Unable to remove dir %s: %s', _dir, e)
                return 1
        return 0

    def _mount_local(self, _dmg: str, _dir: str) -> int:
        self.debug('Mount %s to %s', _dmg, _dir)
        _err = self.indented(self._mkdir, _dir)
        cmd = ['hdiutil', 'mount']
        if self.verbose:
            cmd.append('-verbose')
        cmd.extend([_dmg, '-mountpoint', _dir])
        _err += self.indented(self._exec, cmd).returncode
        return _err

    def _umount_local(self, _dir: str) -> int:
        _err = self._umount(_dir)
        _err += self._rmdir(_dir)
        return _err

    def _umount(self, _dir: str) -> int:
        self.debug('Umount %s', _dir)
        cmd = ['hdiutil', 'eject']
        if self.verbose:
            cmd.append('-verbose')
        cmd.append(_dir)
        return self.indented(self._exec, cmd).returncode

    def _mount_via_ssh(self, _dir: str) -> int:
        for _host in self.remote_hosts:
            self.debug('Select remote host')
            if self.indented(self._exec, ['ssh', '-o', 'ConnectTimeout 2', '-q', _host, 'hostname']).returncode != 0:
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
        if self.unsafe:
            try:
                os.symlink(orig, dest)
            except OSError as e:
                self.error('Unable to symlink %s to %s: %s', orig, dest, e)
                return 1
        return 0

    def _rm(self, fname) -> int:
        self.debug('Remove %s', fname)
        if self.unsafe:
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
        _err += self._mount_via_ssh(f'{self.data_link}/saves')
        _err += self._mount_local(self.bin_dmg, self.bin_dir)
        _err += self._exec([self.main_exe]).returncode
        return _err

    def off(self) -> int:
        _err = self._umount_ssh(f'{self.data_link}/saves')
        _err += self._umount_local(self.bin_dir)
        umount_err = self._umount_local(self.data_link)
        if umount_err == 0:
            if os.path.islink(self.data_link):
                _err += self._rm(self.data_link)
        else:
            _err += umount_err
        return _err


def parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['on', 'off'], default='on', nargs='?')
    parser.add_argument('--pretend', '-p', action='store_true')
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--skip-unmount', '-s', action='store_true')
    return parser.parse_args(argv)


def main(argv: list = sys.argv[1:]):
    cfg = parse_args(argv)
    nwn = NWN(verbose=cfg.verbose, pretend=cfg.pretend)

    if cfg.command == 'off':
        return nwn.off()
    elif cfg.command == 'on':
        _err = nwn.on()
        if not cfg.pretend and not cfg.skip_unmount:
            time.sleep(3)
        if not cfg.skip_unmount:
            _err += nwn.off()
        return _err


if __name__ == '__main__':
    main()
