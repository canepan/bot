import mock
import pytest

from tools.bin.minecraft_ctl import kill_all_instances, list_instances, main, parse_args


@pytest.fixture
def mock_os_chmod(monkeypatch):
    mock_os_chmod = mock.MagicMock(name='chmod')
    monkeypatch.setattr('tools.bin.minecraft_ctl.os.chmod', mock_os_chmod)
    yield mock_os_chmod


@pytest.fixture
def mock_os_kill(monkeypatch):
    mock_os_kill = mock.MagicMock(name='kill')
    monkeypatch.setattr('tools.bin.minecraft_ctl.os.kill', mock_os_kill)
    yield mock_os_kill


@pytest.fixture
def mock_subprocess(monkeypatch):
    mock_subprocess = mock.MagicMock(name='subprocess')
    # 1st is Linux format, 2nd is OSX
    mock_subprocess.check_output.side_effect = [(
        b'''USER       PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND\n'''
        b'''root         1  0.0  0.0 195212  7788 ?        Ss   Oct31   0:40 /sbin/init\n'''
        b'''root         2  0.0  0.0      0     0 ?        S    Oct31   0:00 [kthreadd]\n'''
        b'''root         3  0.0  0.0      0     0 ?        S    Oct31   0:41 [ksoftirqd/0]\n'''
        b'''root         5  0.0  0.0      0     0 ?        S<   Oct31   0:00 [kworker/0:0H]\n'''
        b'''root         7  0.1  0.0      0     0 ?        S    Oct31  80:48 [rcu_sched]\n'''
        b'''root         8  0.0  0.0      0     0 ?        S    Oct31   0:00 [rcu_bh]\n'''
        b'''root         9  0.0  0.0      0     0 ?        S    Oct31   0:11 [migration/0]\n'''
        b'''root        10  0.0  0.0      0     0 ?        S<   Oct31   0:00 [lru-add-drain]\n'''
        b'''root        11  0.0  0.0      0     0 ?        S    Oct31   0:11 [watchdog/0]\n'''
        b'''root        12  0.0  0.0      0     0 ?        S    Oct31   0:00 [cpuhp/0]\n'''
        b'''root        13  0.0  0.0      0     0 ?        S    Oct31   0:00 [cpuhp/1]\n'''
        b'''root        14  0.0  0.0      0     0 ?        S    Oct31   0:09 [watchdog/1]\n'''
        b'''root        42  0.4  0.2      0     0 ?        S    Jan01   0:24 my process name is running\n'''
    ),
    (
        b'''USER              PID  %CPU %MEM      VSZ    RSS   TT  STAT STARTED      TIME COMMAND\n'''
        b'''username         6117  18.5  0.5  4599996  39420   ??  S     9:37am   0:56.15 /System/Library/CoreServices/ReportCrash agent\n'''
        b'''root              570  14.8  0.0  4307204   1276   ??  Rs   12Dec20  73:21.29 /System/Library/PrivateFrameworks/CoreSymbolication.framework/coresymbolicationd\n'''
        b'''root               74   8.5  0.1  4354852  11556   ??  Ss   12Dec20  88:37.14 /usr/libexec/opendirectoryd\n'''
        b'''_coreaudiod       136   3.7  0.1  4314996   4924   ??  Ss   12Dec20 584:23.20 /usr/sbin/coreaudiod\n'''
    )]
    monkeypatch.setattr('tools.bin.minecraft_ctl.subprocess', mock_subprocess)
    yield mock_subprocess


def test_list_instances(mock_subprocess):
    assert list_instances(['process name'], verbose=False) == {42: 'root        42  0.4  0.2      0     0 ?        S    Jan01   0:24 my process name is running'}
    assert list_instances(['ReportCrash agent'], verbose=True) == {6117: 'username         6117  18.5  0.5  4599996  39420   ??  S     9:37am   0:56.15 /System/Library/CoreServices/ReportCrash agent'}


def test_list_instances_not_found(mock_subprocess):
    assert list_instances(['other process name']) == {}
    assert list_instances(['Missing agent']) == {}


def test_kill_all_instances(mock_os_kill, mock_subprocess):
    kill_all_instances(['process name'], signal=12)
    mock_os_kill.assert_called_with(42, 12)
    kill_all_instances(['ReportCrash agent'])
    mock_os_kill.assert_called_with(6117, 15)


@pytest.mark.parametrize('prog_name,launcher,processes,signal', (
    ('minecraft_ctl.py', '/Applications/Minecraft.app/Contents/MacOS/launcher', ('java', 'minecraft'), 15),
    ('diablo3_ctl', '/Volumes/MoviablesX/Mac/Diablo III/Diablo III.app/Contents/MacOS/Diablo III', ('Diablo III',), 15),
    ('docker_ctl', '/Applications/Docker.app/Contents/MacOS/Docker', ('Docker',), 15),
    ('firefox_ctl', '/Applications/Firefox.app/Contents/MacOS/firefox', ('firefox',), 9)
))
def test_parse_args(prog_name, launcher, processes, signal):
    cfg = parse_args(['on'], prog_name)
    assert cfg.command == 'on'
    assert cfg.launcher == launcher
    assert cfg.processes == processes
    assert cfg.kill_signal == signal
    assert not cfg.verbose


def test_parse_args_exc():
    with pytest.raises(SystemExit):
        cfg = parse_args([], 'minecraft_ctl.py')


def test_main_on(mock_os_chmod):
    main(['on'], prog_name='minecraft_ctl')
    print(mock_os_chmod.mock_calls)
    mock_os_chmod.assert_called_with('/Applications/Minecraft.app/Contents/MacOS/launcher', 0o755)
