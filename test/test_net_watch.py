from unittest import mock

import pytest
from click.testing import CliRunner

from tools.bin import net_watch


@pytest.fixture
def mock_run(monkeypatch):
    mock_obj = mock.Mock(name='run', return_value=mock.Mock(returncode=0))
    monkeypatch.setattr('tools.bin.net_watch.subprocess.run', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_rumps(monkeypatch):
    mock_obj = mock.Mock(name='rumps')
    monkeypatch.setattr('tools.bin.net_watch.rumps', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def no_rumps(monkeypatch):
    monkeypatch.setattr('tools.bin.net_watch.rumps', None)


@pytest.fixture
def mock_run_app(monkeypatch):
    mock_obj = mock.Mock(name='run_app')
    monkeypatch.setattr('tools.bin.net_watch.run_app', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_popen(monkeypatch, tmp_path):
    monkeypatch.setattr('tools.bin.net_watch.LOG_FILE', str(tmp_path / 'net_watch.log'))
    mock_obj = mock.Mock(name='Popen', return_value=mock.Mock(pid=42))
    monkeypatch.setattr('tools.bin.net_watch.subprocess.Popen', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def runner():
    return CliRunner()


@pytest.mark.parametrize('returncode,expected', [(0, True), (1, False)])
def test_ping_ok(mock_run, returncode, expected):
    mock_run.return_value = mock.Mock(returncode=returncode)
    assert net_watch.ping_ok('192.0.2.1', timeout=3) is expected
    assert mock_run.call_args[0][0] == ['ping', '-c', '1', '-t', '3', '192.0.2.1']


def test_ping_ok_oserror(mock_run):
    mock_run.side_effect = OSError('no ping')
    assert net_watch.ping_ok('192.0.2.1') is False


def test_ping_state_transitions():
    state = net_watch.PingState(failures=2)
    assert state.update(True) is None  # up, stays up
    assert state.update(False) is None  # first failure: no transition yet
    assert state.update(False) is False  # threshold: down
    assert state.update(False) is None  # still down
    assert state.update(True) is True  # recovery
    assert state.update(True) is None  # still up


def test_ping_state_recovers_counter():
    state = net_watch.PingState(failures=2)
    assert state.update(False) is None
    assert state.update(True) is None  # counter reset without a down transition
    assert state.update(False) is None
    assert state.update(False) is False


def test_main_without_rumps(no_rumps, runner):
    result = runner.invoke(net_watch.main, ['-F'])
    assert result.exit_code != 0
    assert 'rumps is required' in result.output


def test_main_foreground_uses_config_defaults(mock_rumps, mock_run_app, runner, tmp_path):
    config = tmp_path / 'net_watch.cfg'
    config.write_text('[net-watch]\nhost = 192.0.2.99\ninterval = 30\nnotifications = false\n')
    result = runner.invoke(net_watch.main, ['-c', str(config), '-F'])
    assert result.exit_code == 0, result.output
    mock_run_app.assert_called_once_with('192.0.2.99', 30, 2, 2, False)


def test_main_cli_overrides_config(mock_rumps, mock_run_app, runner, tmp_path):
    config = tmp_path / 'net_watch.cfg'
    config.write_text('[net-watch]\nhost = 192.0.2.99\n')
    result = runner.invoke(net_watch.main, ['-c', str(config), '-H', '192.0.2.1', '-F'])
    assert result.exit_code == 0, result.output
    assert mock_run_app.call_args[0][0] == '192.0.2.1'


def test_main_missing_config_uses_defaults(mock_rumps, mock_run_app, runner, tmp_path):
    result = runner.invoke(net_watch.main, ['-c', str(tmp_path / 'missing.cfg'), '-F'])
    assert result.exit_code == 0, result.output
    mock_run_app.assert_called_once_with('1.1.1.1', 5, 2, 2, True)


def test_main_daemonizes_by_default(mock_rumps, mock_popen, runner, tmp_path):
    result = runner.invoke(net_watch.main, ['-c', str(tmp_path / 'missing.cfg')])
    assert result.exit_code == 0, result.output
    assert mock_popen.call_args[0][0][-1] == '--foreground'
    assert 'pid 42' in result.output
