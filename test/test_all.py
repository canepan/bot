from unittest import mock
import pytest

from tools.bin.all import gethostname, main, HOSTS


@pytest.fixture
def mock_run(monkeypatch):
    mock_obj = mock.MagicMock(name='run')
    mock_obj.return_value.returncode = 0
    mock_obj.return_value.stdout = 'my output'
    mock_obj.return_value.stderr = ''
    monkeypatch.setattr('tools.bin.all.run', mock_obj)
    yield mock_obj
    print(mock_obj.mock_calls)


@pytest.fixture
def mock_socket(monkeypatch):
    gethostname.cache_clear()
    mock_obj = mock.MagicMock(name='socket')
    mock_obj.gethostname.return_value = 'phoenix'
    monkeypatch.setattr('tools.bin.all.socket', mock_obj)
    yield mock_obj
    print(mock_obj.mock_calls)


def call_for(hname, cmd):
    return mock.call(
        ['ssh', '-q', '-o StrictHostKeyChecking false', '-o ConnectTimeout 5', hname, cmd],
        stderr=-1,
        stdout=-1,
        universal_newlines=True,
    )


@pytest.mark.skip(reason='Need to mock DNS calls')
def test_main(mock_run, mock_socket):
    cmd = 'ls -l'
    main([cmd])
    mock_run.assert_has_calls(
        [call_for(hname, cmd) for hname in HOSTS['linux'] | HOSTS['mac'] if hname != 'phoenix'], any_order=True
    )
    assert call_for('phoenix', cmd) not in mock_run.call_args_list

    mock_socket.gethostname.assert_called_once_with()


@pytest.mark.skip(reason='Need to mock DNS calls')
def test_main_mac(mock_run, mock_socket, capsys):
    cmd = 'ls -l'
    mock_run.return_value.stderr = 'errors'
    main([cmd, '--mac'])

    mock_socket.gethostname.assert_called_once_with()
    mock_run.assert_has_calls([call_for(hname, cmd) for hname in HOSTS['mac']], any_order=True)
    expected = '\n'.join(f'{hname}: my output\n{hname}: (err) errors' for hname in HOSTS['mac'])
    assert capsys.readouterr().out.rstrip('\n') == expected


@pytest.mark.skip(reason='Need to mock DNS calls')
def test_main_linux(mock_run, mock_socket, capsys):
    cmd = 'ls -l'
    # it works also if remote command returns an error, but produces no output
    mock_run.return_value.returncode = 1
    main([cmd, '--linux'])

    mock_socket.gethostname.assert_called_once_with()
    mock_run.assert_has_calls([call_for(hname, cmd) for hname in HOSTS['linux'] if hname != 'phoenix'], any_order=True)
    assert call_for('phoenix', cmd) not in mock_run.call_args_list
    assert capsys.readouterr().out == ''
