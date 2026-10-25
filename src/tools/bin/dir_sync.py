#!/usr/bin/env python3
"""Reconcile a local and a remote directory over SFTP (paramiko).

For each regular file found on both sides, if the contents differ the older
side is backed up (renamed to `<file>.<YYYYMMDD>`) and then replaced with the
newer copy. Files existing on only one side are copied over as-is.

Backups (and any user-supplied glob) are skipped via the exclusion list, so
previous backups are never compared or propagated.

Config file (TOML, `~/.config/dirsync/config.toml`), CLI options override it:

    host = "nas.home"
    remote-dir = "/srv/keepalived"
    local-dir = "/etc/keepalived"
    exclude = ["*.log", "cache/*"]
    user = "root"
    key-file = "~/.ssh/id_ed25519"
"""

from __future__ import annotations

import fnmatch
import getpass
import hashlib
import posixpath
import stat
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable

import click
import paramiko

from tools.libs.config import ClickConfigReader, ConfigError

APP_NAME = 'dirsync'
DEFAULT_EXCLUDES = ('*.20[0-9][0-9][0-1][0-9][0-3][0-9]', '*~', '*.bak', '*.swp')


@dataclass
class FileInfo:
    """One regular file: size and mtime (epoch seconds)."""

    size: int
    mtime: float


@dataclass
class Change:
    """One reconciliation action."""

    rel: str
    action: str  # 'backup-local' | 'backup-remote' | 'upload' | 'download'
    note: str = ''


class SFTPSide:
    """Remote side of the comparison, over SFTP."""

    def __init__(self, sftp: paramiko.SFTPClient, root: str):
        self.sftp = sftp
        self.root = root.rstrip('/')

    def scan(self) -> dict[str, FileInfo]:
        files: dict[str, FileInfo] = {}
        self._walk(self.root, files)
        return files

    def _walk(self, path: str, files: dict[str, FileInfo]) -> None:
        for entry in self.sftp.listdir_attr(path):
            full = posixpath.join(path, entry.filename)
            if stat.S_ISDIR(entry.st_mode or 0):
                self._walk(full, files)
            elif stat.S_ISREG(entry.st_mode or 0):
                rel = posixpath.relpath(full, self.root)
                files[rel] = FileInfo(size=entry.st_size or 0, mtime=float(entry.st_mtime or 0))

    def md5(self, rel: str) -> str:
        """Stream the remote file through md5; '' on read errors."""
        digest = hashlib.md5()
        try:
            with self.sftp.open(posixpath.join(self.root, rel), 'rb') as fh:
                for chunk in iter(lambda: fh.read(65536), b''):
                    digest.update(chunk)
        except OSError:
            return ''
        return digest.hexdigest()

    def rename(self, src_rel: str, dst_rel: str) -> None:
        self.sftp.rename(posixpath.join(self.root, src_rel), posixpath.join(self.root, dst_rel))

    def put(self, local: Path, rel: str) -> None:
        self.sftp.put(str(local), posixpath.join(self.root, rel))

    def get(self, rel: str, local: Path) -> None:
        self.sftp.get(posixpath.join(self.root, rel), str(local))


def local_scan(root: Path) -> dict[str, FileInfo]:
    """Recursively list regular files under `root`, relative to it.

    >>> root = getfixture('tmp_path')  # doctest: +SKIP
    """
    files: dict[str, FileInfo] = {}
    for path in sorted(root.rglob('*')):
        if path.is_file() and not path.is_symlink():
            st = path.stat()
            files[path.relative_to(root).as_posix()] = FileInfo(size=st.st_size, mtime=st.st_mtime)
    return files


def is_excluded(rel: str, patterns: tuple[str, ...]) -> bool:
    """True if `rel` matches any exclusion glob (on the basename or full relative path).

    >>> is_excluded('sub/a.20251025', DEFAULT_EXCLUDES)
    True
    >>> is_excluded('sub/a.txt', DEFAULT_EXCLUDES)
    False
    >>> is_excluded('logs/a.log', ('*.log',))
    True
    >>> is_excluded('cache/x.bin', ('cache/*',))
    True
    """
    name = PurePosixPath(rel).name
    return any(fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel, pat) for pat in patterns)


def content_changed(local: FileInfo, remote: FileInfo) -> bool:
    """Fast path: same size and close mtime means unchanged.

    >>> content_changed(FileInfo(3, 100), FileInfo(3, 100))
    False
    >>> content_changed(FileInfo(3, 100), FileInfo(4, 100))
    True
    """
    if local.size != remote.size:
        return True
    return abs(local.mtime - remote.mtime) > 2.0


def plan_changes(
    local: dict[str, FileInfo],
    remote: dict[str, FileInfo],
    excludes: tuple[str, ...],
    today: str,
    local_md5: Callable[[str], str],
    remote_md5: Callable[[str], str],
) -> list[Change]:
    """Decide what to back up / upload / download.

    md5 callables are used only when size+mtime look changed, to avoid acting
    on timestamp skew alone.
    """
    changes: list[Change] = []
    for rel in sorted(set(local) | set(remote)):
        if is_excluded(rel, excludes):
            continue
        lin, rin = local.get(rel), remote.get(rel)
        if lin and not rin:
            changes.append(Change(rel, 'upload', 'missing on remote'))
        elif rin and not lin:
            changes.append(Change(rel, 'download', 'missing locally'))
        elif lin and rin and content_changed(lin, rin):
            lm, rm = local_md5(rel), remote_md5(rel)
            if lm and rm and lm == rm:
                continue  # mtime skew only, contents identical
            if lin.mtime >= rin.mtime:
                changes.append(Change(rel, 'backup-remote', f'-> {rel}.{today}'))
                changes.append(Change(rel, 'upload', 'local is newer'))
            else:
                changes.append(Change(rel, 'backup-local', f'-> {rel}.{today}'))
                changes.append(Change(rel, 'download', 'remote is newer'))
    return changes


def local_md5(root: Path, rel: str) -> str:
    """md5 of a local file; '' on read errors."""
    try:
        return hashlib.md5((root / rel).read_bytes()).hexdigest()
    except OSError:
        return ''


@dataclass
class SyncConfig:
    host: str
    remote_dir: str
    local_dir: Path
    user: str = field(default_factory=getpass.getuser)
    port: int = 22
    key_file: Path | None = None
    exclude: tuple[str, ...] = ()
    dry_run: bool = False


def connect(cfg: SyncConfig) -> paramiko.SFTPClient:
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.WarningPolicy())
    client.connect(
        cfg.host,
        port=cfg.port,
        username=cfg.user,
        key_filename=str(cfg.key_file.expanduser()) if cfg.key_file else None,
    )
    return client.open_sftp()


def apply_changes(changes: list[Change], cfg: SyncConfig, side: SFTPSide, today: str) -> None:
    for change in changes:
        click.echo(f'{"DRY-RUN " if cfg.dry_run else ""}{change.action:14} {change.rel} {change.note}')
        if cfg.dry_run:
            continue
        if change.action == 'backup-local':
            (cfg.local_dir / change.rel).rename(cfg.local_dir / f'{change.rel}.{today}')
        elif change.action == 'backup-remote':
            side.rename(change.rel, f'{change.rel}.{today}')
        elif change.action == 'upload':
            side.put(cfg.local_dir / change.rel, change.rel)
        elif change.action == 'download':
            side.get(change.rel, cfg.local_dir / change.rel)


@ClickConfigReader(APP_NAME).option(envvar='DIRSYNC_CONFIG')
@click.command()
@click.option('-H', '--host', required=True, help='Remote host (SSH)')
@click.option('-u', '--user', default=None, show_default='current user', help='SSH user')
@click.option('-p', '--port', default=22, show_default=True, help='SSH port')
@click.option('-k', '--key-file', type=click.Path(dir_okay=False, path_type=Path), default=None, help='SSH private key')
@click.option('-l', '--local-dir', type=click.Path(file_okay=False, path_type=Path), required=True, help='Local root')
@click.option('-r', '--remote-dir', default=None, show_default='same as --local-dir', help='Remote root on the server')
@click.option(
    '-x',
    '--exclude',
    multiple=True,
    help=f'Extra exclusion glob (repeatable). Built-in: {", ".join(DEFAULT_EXCLUDES)}',
)
@click.option('-n', '--dry-run', is_flag=True, help='Show what would change, without touching anything')
def main(
    host: str,
    user: str | None,
    port: int,
    key_file: Path | None,
    local_dir: Path,
    remote_dir: str | None,
    exclude: tuple[str, ...],
    dry_run: bool,
) -> None:
    """Reconcile LOCAL-DIR with REMOTE-DIR on HOST, backing up the older side."""
    cfg = SyncConfig(
        host=host,
        remote_dir=remote_dir or str(local_dir),
        local_dir=local_dir.expanduser(),
        user=user or getpass.getuser(),
        port=port,
        key_file=key_file,
        exclude=DEFAULT_EXCLUDES + tuple(exclude),
        dry_run=dry_run,
    )
    if not cfg.local_dir.is_dir():
        raise ConfigError(f'local dir not found: {cfg.local_dir}')

    today = datetime.now().strftime('%Y%m%d')
    local_files = local_scan(cfg.local_dir)

    sftp = connect(cfg)
    try:
        side = SFTPSide(sftp, cfg.remote_dir)
        remote_files = side.scan()
        changes = plan_changes(
            local_files, remote_files, cfg.exclude, today, lambda rel: local_md5(cfg.local_dir, rel), side.md5
        )
        if not changes:
            click.echo('Already in sync')
            return
        apply_changes(changes, cfg, side, today)
    finally:
        sftp.close()


if __name__ == '__main__':
    main(sys.argv[1:])
