import io
import os
import stat as stat_mod
from datetime import datetime
from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner

from tools.bin import dir_sync as ds

TODAY = datetime.now().strftime('%Y%m%d')


# ---------------------------------------------------------------------------
# Fake SFTP: in-memory remote filesystem, the only test double besides connect
# ---------------------------------------------------------------------------


class FakeSFTP:
    """Remote files as {path: bytes}; records rename/put/get for assertions."""

    def __init__(self, files: dict[str, bytes], mtimes: dict[str, float]):
        self.files = dict(files)
        self.mtimes = dict(mtimes)
        self.renamed: list[tuple[str, str]] = []
        self.put_calls: list[tuple[str, str]] = []
        self.get_calls: list[tuple[str, str]] = []

    def listdir_attr(self, path: str):
        prefix = path.rstrip('/') + '/'
        seen = set()
        entries = []
        for full in sorted(self.files):
            if not full.startswith(prefix):
                continue
            rest = full[len(prefix) :]
            head = rest.split('/')[0]
            if head in seen:
                continue
            seen.add(head)
            e = mock.Mock(name=f'attr:{head}')
            e.filename = head
            if '/' in rest:
                e.st_mode = stat_mod.S_IFDIR | 0o755
                e.st_size = 0
                e.st_mtime = 0
            else:
                e.st_mode = stat_mod.S_IFREG | 0o644
                e.st_size = len(self.files[full])
                e.st_mtime = self.mtimes.get(full, 0)
            entries.append(e)
        return entries

    def open(self, path: str, mode: str = 'rb'):
        return io.BytesIO(self.files[path])

    def rename(self, src: str, dst: str):
        self.renamed.append((src, dst))
        self.files[dst] = self.files.pop(src)
        self.mtimes[dst] = self.mtimes.pop(src)

    def put(self, local: str, remote: str):
        self.put_calls.append((local, remote))
        self.files[remote] = Path(local).read_bytes()

    def get(self, remote: str, local: str):
        self.get_calls.append((remote, local))
        Path(local).write_bytes(self.files[remote])

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def connect():
    """The only mock: the SSH boundary. Tests set connect.return_value = FakeSFTP."""
    connect_mock = mock.Mock(name='connect')
    with mock.patch.object(ds, 'connect', connect_mock):
        yield connect_mock
    print(f'{connect_mock} {connect_mock.mock_calls}')


@pytest.fixture
def local_tree(tmp_path):
    """A real local tree: same/changed/only_local/older_local files."""
    root = tmp_path / 'local'
    (root / 'sub').mkdir(parents=True)
    files = {
        'same.txt': (b'same', 1000),
        'changed.txt': (b'local is newer', 1000),
        'only_local.txt': (b'only here', 900),
        'sub/older_local.txt': (b'old local copy', 100),
    }
    for rel, (data, mtime) in files.items():
        f = root / rel
        f.write_bytes(data)
        os.utime(f, (mtime, mtime))
    return root


@pytest.fixture
def remote_tree():
    """The matching FakeSFTP remote tree."""
    return FakeSFTP(
        {
            '/remote/same.txt': b'same',
            '/remote/changed.txt': b'old!',
            '/remote/only_remote.txt': b'only remote',
            '/remote/sub/older_local.txt': b'newer remote copy',
        },
        {
            '/remote/same.txt': 1000,
            '/remote/changed.txt': 500,  # older than local
            '/remote/only_remote.txt': 700,
            '/remote/sub/older_local.txt': 2000,  # newer than local
        },
    )


# ---------------------------------------------------------------------------
# Pure-logic unit tests: no files, no mocks
# ---------------------------------------------------------------------------


def test_is_excluded():
    assert ds.is_excluded('a.20251025', ds.DEFAULT_EXCLUDES)
    assert ds.is_excluded('sub/file.bak', ds.DEFAULT_EXCLUDES)
    assert not ds.is_excluded('sub/file.txt', ds.DEFAULT_EXCLUDES)
    assert ds.is_excluded('sub/file.log', ('*.log',))


@pytest.mark.parametrize(
    'local,remote,expected',
    [
        (ds.FileInfo(1, 100), ds.FileInfo(1, 101), False),
        (ds.FileInfo(1, 100), ds.FileInfo(2, 100), True),
        (ds.FileInfo(1, 100), ds.FileInfo(1, 200), True),
    ],
)
def test_content_changed(local, remote, expected):
    assert ds.content_changed(local, remote) == expected


def test_plan_changes():
    # a.txt: remote newer (download); newer.txt: local newer (upload)
    local = {'a.txt': ds.FileInfo(1, 100), 'newer.txt': ds.FileInfo(1, 300), 'gone_remote.txt': ds.FileInfo(1, 1)}
    remote = {'a.txt': ds.FileInfo(1, 300), 'newer.txt': ds.FileInfo(1, 100), 'gone_local.txt': ds.FileInfo(1, 1)}
    changes = ds.plan_changes(local, remote, ds.DEFAULT_EXCLUDES, '20251025', lambda r: 'L', lambda r: 'R')
    got = [(c.rel, c.action) for c in changes]
    assert ('a.txt', 'backup-local') in got
    assert ('a.txt', 'download') in got
    assert ('newer.txt', 'backup-remote') in got
    assert ('newer.txt', 'upload') in got
    assert ('gone_remote.txt', 'upload') in got
    assert ('gone_local.txt', 'download') in got


def test_plan_changes_same_md5_skipped():
    local = {'a.txt': ds.FileInfo(1, 300)}
    remote = {'a.txt': ds.FileInfo(1, 100)}
    changes = ds.plan_changes(local, remote, (), '20251025', lambda r: 'same', lambda r: 'same')
    assert changes == []


def test_plan_changes_excludes_backups():
    local = {'a.txt.20251024': ds.FileInfo(1, 300)}
    remote = {}
    assert ds.plan_changes(local, remote, ds.DEFAULT_EXCLUDES, '20251025', lambda r: '', lambda r: '') == []


# ---------------------------------------------------------------------------
# Real-filesystem contract tests for local_scan / local_md5
# ---------------------------------------------------------------------------


def test_local_scan(tmp_path):
    (tmp_path / 'sub').mkdir()
    f = tmp_path / 'sub' / 'a.txt'
    f.write_text('hello')
    os.utime(f, (1000, 1000))
    assert ds.local_scan(tmp_path) == {'sub/a.txt': ds.FileInfo(5, 1000)}


def test_local_md5(tmp_path):
    (tmp_path / 'a.txt').write_text('hello')
    assert ds.local_md5(tmp_path, 'a.txt') == '5d41402abc4b2a76b9719d911017c592'
    assert ds.local_md5(tmp_path, 'missing.txt') == ''


# ---------------------------------------------------------------------------
# CLI tests: real local tree + FakeSFTP, only connect mocked
# ---------------------------------------------------------------------------


def test_main_already_in_sync(runner, connect, tmp_path):
    f = tmp_path / 'same.txt'
    f.write_bytes(b'same')
    os.utime(f, (1000, 1000))
    connect.return_value = FakeSFTP({'/remote/same.txt': b'same'}, {'/remote/same.txt': 1000})
    result = runner.invoke(ds.main, ['-H', 'nas', '-l', str(tmp_path), '-r', '/remote'], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert 'Already in sync' in result.output


def test_main_dry_run(runner, connect, local_tree, remote_tree):
    connect.return_value = remote_tree
    result = runner.invoke(ds.main, ['-H', 'nas', '-l', str(local_tree), '-r', '/remote', '-n'])
    assert result.exit_code == 0, result.output
    assert 'DRY-RUN' in result.output
    assert 'changed.txt' in result.output
    assert 'only_local.txt' in result.output
    assert 'only_remote.txt' in result.output
    assert remote_tree.put_calls == []
    assert remote_tree.get_calls == []
    assert remote_tree.renamed == []


def test_main_applies_changes(runner, connect, local_tree, remote_tree):
    connect.return_value = remote_tree
    result = runner.invoke(ds.main, ['-H', 'nas', '-l', str(local_tree), '-r', '/remote'])
    assert result.exit_code == 0, result.output

    # remote older file backed up, then local uploaded
    assert ('/remote/changed.txt', f'/remote/changed.txt.{TODAY}') in remote_tree.renamed
    assert remote_tree.files[f'/remote/changed.txt.{TODAY}'] == b'old!'
    assert (str(local_tree / 'changed.txt'), '/remote/changed.txt') in remote_tree.put_calls
    assert remote_tree.files['/remote/changed.txt'] == b'local is newer'

    # local older file backed up, then remote downloaded
    backup = local_tree / f'sub/older_local.txt.{TODAY}'
    assert backup.exists()
    assert backup.read_bytes() == b'old local copy'
    assert ('/remote/sub/older_local.txt', str(local_tree / 'sub/older_local.txt')) in remote_tree.get_calls
    assert (local_tree / 'sub/older_local.txt').read_bytes() == b'newer remote copy'

    # only_remote.txt downloaded; only_local.txt uploaded
    assert (local_tree / 'only_remote.txt').read_bytes() == b'only remote'
    assert remote_tree.files['/remote/only_local.txt'] == b'only here'


def test_main_missing_local_dir(runner):
    result = runner.invoke(ds.main, ['-H', 'nas', '-l', '/nonexistent-dir', '-r', '/remote'])
    assert result.exit_code != 0
    assert isinstance(result.exception, ds.ConfigError)
    assert 'local dir not found' in str(result.exception)


def test_main_remote_dir_defaults_to_local(runner, connect, tmp_path):
    f = tmp_path / 'same.txt'
    f.write_bytes(b'same')
    os.utime(f, (1000, 1000))
    connect.return_value = FakeSFTP({f'{tmp_path}/same.txt': b'same'}, {f'{tmp_path}/same.txt': 1000})
    result = runner.invoke(ds.main, ['-H', 'nas', '-l', str(tmp_path)], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert 'Already in sync' in result.output
    cfg = connect.call_args[0][0]
    assert cfg.remote_dir == str(tmp_path)
