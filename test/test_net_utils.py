import socket
from unittest import mock

import pytest

from tools.libs import net_utils


@pytest.fixture
def mock_socket(monkeypatch):
    mock_socket = mock.Mock(name='socket')
    mock_socket.gethostbyname.side_effect = ['1.1.1.1', '2.2.2.2']
    mock_socket.gethostname.return_value = 'local_host'
    monkeypatch.setattr('tools.libs.net_utils.socket', mock_socket)
    mock_socket.gaierror = socket.gaierror
    yield mock_socket
    print(f'{mock_socket} {mock_socket.mock_calls}')


def test_hosts_if_not_me(mock_socket):
    mock_socket.gethostname.return_value = 'myfqdn'
    assert list(net_utils.hosts_if_not_me(['myfqdn'])) == []
    assert list(net_utils.hosts_if_not_me(['other', 'myfqdn'])) == [net_utils.Host(hostname='other', ip='1.1.1.1')]


def test_hosts_if_not_me_exc(mock_socket):
    net_utils.gethostbyname.cache_clear()
    mock_socket.gethostname.return_value = 'myfqdn'
    # mock_socket.gethostbyname.side_effect = [socket.gaierror]
    assert list(net_utils.hosts_if_not_me(['myfqdn'])) == []
    net_utils.gethostbyname.cache_clear()
    mock_socket.gethostbyname.side_effect = socket.gaierror
    assert list(net_utils.hosts_if_not_me(['other', 'myfqdn'])) == []
    net_utils.gethostbyname.cache_clear()
    mock_socket.gethostbyname.side_effect = [socket.gaierror, '1.1.1.1']
    assert list(net_utils.hosts_if_not_me(['this', 'other', 'myfqdn'])) == [
        net_utils.Host(hostname='other', ip='1.1.1.1')
    ]


def test_ip_if_not_local(mock_socket):
    assert net_utils.ip_if_not_local('local_host') is None
    assert net_utils.ip_if_not_local('test') == '2.2.2.2'
