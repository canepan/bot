import pytest
from unittest import mock


@pytest.fixture
def mock_os(monkeypatch):
    mock_obj = mock.Mock(name='os')
    mock_obj.path.expanduser.side_effect = lambda x: x.replace('~', 'HOME')
    monkeypatch.setattr('tools.bin.backup_mysql.os', mock_obj)
    monkeypatch.setattr('tools.bin.nwn.os', mock_obj)
    monkeypatch.setattr('tools.bin.openvpn_log.os', mock_obj)
    yield mock_obj
    print(f'{mock_obj}: {mock_obj.mock_calls}')
