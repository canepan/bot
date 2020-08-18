import mock
import pytest

from tools.libs.vip_utils import is_proxy


@pytest.fixture
def mock_socket(monkeypatch):
    mock_socket = mock.Mock(name='socket')
    monkeypatch.setattr('tools.libs.vip_utils.socket', mock_socket)
    mock_socket.gethostbyname.return_value = '192.168.1.1'
    yield mock_socket


@pytest.fixture
def mock_subprocess(monkeypatch):
    mock_subprocess = mock.MagicMock(name='subprocess')
    mock_subprocess.check_output.return_value = b'''
    2: eth0    inet 192.168.19.65/24 scope global secondary eth0\       valid_lft forever preferred_lft forever
    2: eth0    inet 192.168.19.66/24 scope global secondary eth0\       valid_lft forever preferred_lft forever
    2: eth0    inet 192.168.19.67/24 scope global secondary eth0\       valid_lft forever preferred_lft forever
    '''
    monkeypatch.setattr('tools.libs.vip_utils.subprocess', mock_subprocess)
    yield mock_subprocess


def test_is_proxy_false(mock_socket, mock_subprocess):
    assert not is_proxy()


def test_is_proxy_false2(mock_socket, mock_subprocess):
    mock_socket.gethostbyname.return_value = '192.168.19.80'
    assert not is_proxy()


def test_is_proxy(mock_socket, mock_subprocess):
    mock_subprocess.check_output.return_value = (
        b'2: eth0    inet 192.168.19.80/24 scope global secondary eth0\       valid_lft forever preferred_lft forever'
    )
    mock_socket.gethostbyname.return_value = '192.168.19.80'
    assert is_proxy()
