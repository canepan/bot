from unittest import mock

import pytest

from tools.bin.backup_mysql import main


@pytest.fixture
def mock_datetime(monkeypatch):
    mock_obj = mock.Mock(name='datetime')
    monkeypatch.setattr('tools.bin.backup_mysql.datetime', mock_obj)
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


# * mysqldup creates a (temp) file T
# * there may be a previous file P (must be saved if size delta > 10%)
# * the size difference between the new (T) and the previous (P) may be less than 10%
# * the final file (if size != 0) will be named P
@pytest.mark.parametrize('isfile_P', (True, False))
@pytest.mark.parametrize('file_size_P,file_size_T', ((10, 100), (100, 101), (120, 0)))
def test_main(mock_datetime, mock_os, mock_subprocess, mock_tempfile, file_size_P, file_size_T, isfile_P):
    rename_calls = []
    remove_calls = []
    final_file = f'/mnt/opt/backup/mysql/{mock_os.uname.return_value.nodename}_all_dump.sql.gz'
    saved_file = f'{final_file}.{mock_datetime.now.return_value.strftime.return_value}'
    mock_os.stat.side_effect = {
        final_file: mock.Mock(st_size=file_size_P) if isfile_P else FileNotFoundError(),
        mock_tempfile.return_value.name: mock.Mock(st_size=file_size_T),
    }.get
    mock_os.path.isfile.return_value = isfile_P
    main([])
    mock_subprocess.Popen.assert_called_with(
        ['mysqldump', '-A', '-S', '/var/run/mysqld/mysqld.sock'], stdout=mock_subprocess.PIPE
    )
    if isfile_P and abs(file_size_P - file_size_T) / file_size_P > 0.1:
        rename_calls.append(mock.call(final_file, saved_file))
    if file_size_T == 0:
        if isfile_P:
            remove_calls.append(mock.call(mock_tempfile.return_value.name))
    else:
        rename_calls.append(mock.call(mock_tempfile.return_value.name, final_file))
    mock_os.rename.assert_has_calls(rename_calls)
    mock_os.remove.assert_has_calls(remove_calls)
