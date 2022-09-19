from unittest import mock
import pytest

from tools.libs import stools_defaults


@pytest.fixture
def mock_socket(monkeypatch):
    mock_socket = mock.Mock(name='socket')
    mock_socket.gethostbyname.side_effect = ['1.1.1.1', '2.2.2.2']
    mock_socket.gethostname.return_value = 'local_host'
    monkeypatch.setattr('tools.libs.net_utils.socket', mock_socket)
    yield mock_socket


def test_ip_if_not_local(mock_socket):
    assert stools_defaults.ip_if_not_local('local_host') is None
    assert stools_defaults.ip_if_not_local('test') == '2.2.2.2'


def test_parse_args():
    cfg = stools_defaults.parse_args(['-v', 'test'], {'filenames': {'nargs': '+'}})
    assert cfg.verbose is True
    assert cfg.filenames == ['test']
