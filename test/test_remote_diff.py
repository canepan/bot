import io
from contextlib import contextmanager
from unittest import mock

import pytest
from click.testing import CliRunner

from tools.bin import remote_diff as rd

RSYNC_OUTPUT = """\
.f..t...... same_attrs.txt
>fcsT...... changed.txt
>f+++++++ new_on_remote.txt
"""


class FakeSFTP:
    """Remote files as {path: bytes}."""

    def __init__(self, files: dict[str, bytes]):
        self.files = dict(files)

    def open(self, path: str, mode: str = 'r'):
        return io.BytesIO(self.files[path])


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_rsync(monkeypatch):
    mock_obj = mock.Mock(name='check_output', return_value=RSYNC_OUTPUT)
    monkeypatch.setattr(rd, 'check_output', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def fake_sftp(monkeypatch):
    sftp = FakeSFTP(
        {
            '/remote/changed.txt': b'line1\nremote version\nline3\n',
            '/remote/new_on_remote.txt': b'brand new\n',
        }
    )

    @contextmanager
    def client(host: str):
        yield sftp

    monkeypatch.setattr(rd, 'sftp_client', client)
    yield sftp


def test_pathspec_parse():
    assert rd.PathSpec.parse('nas:/srv/etc') == rd.PathSpec(host='nas', path='/srv/etc')
    assert rd.PathSpec.parse('/etc') == rd.PathSpec(host=None, path='/etc')
    assert rd.PathSpec.parse('nas:') == rd.PathSpec(host='nas', path='.')


def test_read_file_local(tmp_path):
    (tmp_path / 'f.txt').write_text('local content\n')
    spec = rd.PathSpec(host=None, path=str(tmp_path))
    assert rd.read_file(spec, 'f.txt') == 'local content\n'


def test_main_quiet_shows_itemized_only(runner, mock_rsync):
    result = runner.invoke(rd.main, ['/local', 'nas:/remote'])
    assert result.exit_code == 0, result.output
    assert 'changed.txt' in result.output
    assert 'Legend' in result.output
    assert '@@' not in result.output  # no diff without --verbose
    mock_rsync.assert_called_once_with(['rsync', '-rtni', '/local', 'nas:/remote'], universal_newlines=True)


def test_main_verbose_diffs_changed_files(runner, mock_rsync, fake_sftp, tmp_path):
    (tmp_path / 'changed.txt').write_text('line1\nlocal version\nline3\n')
    result = runner.invoke(rd.main, [str(tmp_path), 'nas:/remote', '-v'])
    assert result.exit_code == 0, result.output
    assert '-local version' in result.output
    assert '+remote version' in result.output
    # new file on remote: local side is a placeholder, remote side shows as added
    assert '+brand new' in result.output
    assert 'new_on_remote.txt' in result.output
