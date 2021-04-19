import mock
import pytest

from tools.bin.backup_mysql import main


@pytest.fixture
def mock_datetime(monkeypatch):
    mock_obj = mock.Mock(name='datetime')
    monkeypatch.setattr('tools.bin.backup_mysql.datetime', mock_obj)
    yield mock_obj


@pytest.fixture
def mock_os(monkeypatch):
    mock_obj = mock.Mock(name='os')
    # mock_obj.stat.side_effect = [
    #     mock.Mock(st_size=10),
    #     mock.Mock(st_size=100),
    #     mock.Mock(st_size=101),
    #     mock.Mock(st_size=102),
    # ]
    monkeypatch.setattr('tools.bin.backup_mysql.os', mock_obj)
    yield mock_obj


@pytest.fixture
def mock_subprocess(monkeypatch):
    mock_obj = mock.Mock(name='subprocess')
    monkeypatch.setattr('tools.bin.backup_mysql.subprocess', mock_obj)
    yield mock_obj


@pytest.fixture
def mock_tempfile(monkeypatch):
    mock_obj = mock.Mock(name='tempfile.NamedTemporaryFile')
    monkeypatch.setattr('tools.bin.backup_mysql.tempfile.NamedTemporaryFile', mock_obj)
    yield mock_obj


@pytest.mark.parametrize('file_sizes', ((10, 100),))
def test_main(mock_datetime, mock_os, mock_subprocess, mock_tempfile, file_sizes):
    mock_os.stat.side_effect = [
        mock.Mock(st_size=file_sizes[0]),
        mock.Mock(st_size=file_sizes[1]),
    ]
    main([])
    for m in (mock_os, mock_subprocess, mock_tempfile):
        print(m.mock_calls)
    final_file = f'/mnt/opt/backup/mysql/{mock_os.uname.return_value.nodename}_all_dump.sql.gz'
    saved_file = f'{final_file}.{mock_datetime.now.return_value.strftime.return_value}'
    mock_os.rename.assert_called_with(mock_tempfile.return_value.name, final_file)
    mock_os.rename.assert_has_calls([mock.call(final_file, saved_file)])
