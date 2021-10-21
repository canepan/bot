from unittest import mock
import pytest

from tools.bin.total_block import main, user_if_not_me


@pytest.fixture
def mock_getpass(monkeypatch):
    mock_getpass = mock.Mock(name='getpass')
    mock_getpass.getuser.return_value = 'testuser'
    monkeypatch.setattr('tools.bin.total_block.getpass', mock_getpass)
    yield mock_getpass


@pytest.fixture
def mock_ip_if_not_local(monkeypatch):
    mock_ip_if_not_local = mock.Mock(name='ip_if_not_local')
    mock_ip_if_not_local.side_effect = ['10.1.1.1', None]
    monkeypatch.setattr('tools.bin.total_block.ip_if_not_local', mock_ip_if_not_local)
    yield mock_ip_if_not_local


@pytest.fixture
def mock_run(monkeypatch):
    mock_run = mock.Mock(name='run')
    monkeypatch.setattr('tools.bin.total_block.subprocess.run', mock_run)
    yield mock_run


def test_user_if_not_me(mock_getpass):
    assert user_if_not_me('testuser') is None
    assert user_if_not_me('otheruser') == 'otheruser'


def test_main(mock_run, mock_ip_if_not_local):
    main(['on'])
    assert mock_run.mock_calls == []


def test_main_unsafe(mock_run, mock_getpass, mock_ip_if_not_local):
    main(['--unsafe', 'off'])
    cmd = mock_run.mock_calls[0].args[0]
    # name, args, kwargs = mock_run.mock_calls[0]
    cmd = mock_run.mock_calls[0][1][0]
    name, args, kwargs = mock_run.mock_calls[0]
    assert cmd[0] == 'ssh'
    cmd = mock_run.mock_calls[1][1][0]
    assert cmd[0] == 'sudo'
    mock_getpass.getuser.return_value = 'root'


def test_main_unsafe_root(mock_run, mock_getpass, mock_ip_if_not_local):
    mock_getpass.getuser.return_value = 'root'
    main(['--unsafe', 'off'])
    cmd = mock_run.mock_calls[0][1][0]
    assert cmd[0] == 'ssh'
    cmd = mock_run.mock_calls[1][1][0]
    assert cmd[0] == 'bash'
    assert cmd[2].startswith('grep')
