from unittest import mock

import pytest

from tools.bin.minecraft_ctl import DEFAULTS, ProcessManager, main, parse_args


def chmod(*args):
    if not isinstance(args[0], str):
        raise TypeError('Mock chmod {}'.format(args))


def os_stat(*args):
    if not isinstance(args[0], str):
        raise TypeError('Mock stat {}'.format(args))
    return mock.MagicMock(name='stat')


@pytest.fixture
def mock_os_chmod(monkeypatch):
    mock_obj = mock.MagicMock(name='chmod')
    mock_obj.side_effect = chmod
    monkeypatch.setattr('tools.bin.minecraft_ctl.os.chmod', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_os_kill(monkeypatch):
    mock_obj = mock.MagicMock(name='kill')
    monkeypatch.setattr('tools.bin.minecraft_ctl.os.kill', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_os_stat(monkeypatch):
    mock_obj = mock.MagicMock(name='stat')
    mock_obj.side_effect = os_stat
    monkeypatch.setattr('tools.bin.minecraft_ctl.os.stat', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_subprocess(monkeypatch):
    mock_obj = mock.MagicMock(name='subprocess')
    # 1st is Linux format, 2nd is OSX
    mock_obj.check_output.side_effect = (
        (
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
            b'''username         6117  18.5  0.5  4599996  39420   ??  S     9:37am   0:56.15 '''
            b'''/System/Library/CoreServices/ReportCrash agent\n'''
            b'''root              570  14.8  0.0  4307204   1276   ??  Rs   12Dec20  73:21.29 '''
            b'''/System/Library/PrivateFrameworks/CoreSymbolication.framework/coresymbolicationd\n'''
            b'''root               74   8.5  0.1  4354852  11556   ??  Ss   12Dec20  88:37.14 '''
            b'''/usr/libexec/opendirectoryd\n'''
            b'''_coreaudiod       136   3.7  0.1  4314996   4924   ??  Ss   12Dec20 584:23.20 '''
            b'''/usr/sbin/coreaudiod\n'''
            b'''nicola 1234 lunar_client\n'''
            b'''nicola          46102   0.0  0.3  4336000  22856   ??  Ss   11:47am   0:00.09 '''
            b'''/Applications/Lunar Client.app/Contents/MacOS/something\n'''
            b'''nicola          46101   0.0  0.3  5385144  25132   ??  Ss   11:47am   0:00.09 '''
            b'''/Applications/Safari.app/Contents/PlugIns/CacheDeleteExtension.appex/Contents/MacOS/xxx\n'''
            b'''nicola          46100   0.0  0.2  4334920  15876   ??  S    11:47am   0:00.06 '''
            b'''/Applications/iBooks.app/Contents/PlugIns/iBooksCacheDelete.appex/Contents/MacOS/iBooksCacheDelete\n'''
        ),
        (b''),
    )
    monkeypatch.setattr('tools.bin.minecraft_ctl.subprocess', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_log():
    return mock.Mock(name='Logger')


def test_list_instances(mock_subprocess, mock_log):
    assert ProcessManager(['process name'], mock_log, signal=15, pretend=True).status() == {
        42: 'root        42  0.4  0.2      0     0 ?        S    Jan01   0:24 my process name is running'
    }
    assert ProcessManager(['ReportCrash agent'], mock_log, signal=15, pretend=False).status() == {
        6117: 'username         6117  18.5  0.5  4599996  39420   ??  S     9:37am   0:56.15 '
        '/System/Library/CoreServices/ReportCrash agent'
    }


def test_list_instances_not_found(mock_subprocess, mock_log):
    assert ProcessManager(['other process name'], mock_log).status() == {}
    assert ProcessManager(['Missing agent'], mock_log).status() == {}


def test_kill_all_instances(mock_os_kill, mock_subprocess, mock_log):
    ProcessManager(['process name'], mock_log, signal=12, pretend=False).deny()
    mock_os_kill.assert_called_with(42, 12)
    ProcessManager(['ReportCrash agent'], mock_log, signal=15, pretend=False).deny()
    mock_os_kill.assert_called_with(6117, 15)


def test_kill_all_instances_pretend(mock_os_kill, mock_subprocess, mock_log):
    ProcessManager(['process name'], mock_log, signal=12, pretend=True).deny()
    mock_os_kill.assert_not_called()


@pytest.mark.parametrize('command', ('on', 'off', 'status'))
@pytest.mark.parametrize(
    'prog_name,launcher,processes,signal',
    (
        ('docker_ctl', '/Applications/Docker.app/Contents/MacOS/Docker', ('Docker',), 15),
        ('firefox_ctl', '/Applications/Firefox.app/Contents/MacOS/firefox', (r'Firefox\.app.*firefox',), 9),
        (
            'minecraft_ctl',
            [
                '/Applications/Minecraft.app/Contents/MacOS/launcher',
                '/Applications/Lunar Client.app/Contents/MacOS/Lunar Client',
                '/Applications/Badlion Client.app/Contents/MacOS/Badlion Client',
            ],
            ('java.*mojang', '[Mm]inecraft[^_]', '[Ll]unar', 'Badlion'),
            9,
        ),
    ),
)
def test_parse_args(command, prog_name, launcher, processes, signal):
    cfg = parse_args([command], prog_name)
    assert cfg.command == command
    assert launcher == cfg.launcher or launcher in cfg.launcher
    assert cfg.processes == processes
    assert cfg.kill_signal == signal
    assert not cfg.verbose
    assert not cfg.pretend

    cfg = parse_args([command, '--pretend', '-v'], prog_name)
    assert cfg.command == command
    assert launcher == cfg.launcher or launcher in cfg.launcher
    assert cfg.processes == processes
    assert cfg.kill_signal == signal
    assert cfg.verbose
    assert cfg.pretend


def test_parse_args_exc():
    with pytest.raises(SystemExit):
        parse_args([], 'minecraft_ctl.py')


def test_main_on(mock_os_chmod, mock_subprocess):
    main(['on'], prog_name='minecraft_ctl')
    mock_os_chmod.assert_has_calls([mock.call('/Applications/Minecraft.app/Contents/MacOS/launcher', 0o755)])
    mock_subprocess.assert_has_calls(
        [
            mock.call.check_output(
                [
                    'ssh',
                    '-i',
                    '/Users/nicola/.ssh/mt_remote',
                    'manage_internet@mt',
                    '/ip firewall address-list disable numbers=(10, 11)',
                ],
                stderr=mock_subprocess.PIPE,
            ),
            mock.call.check_output(
                [
                    'ssh',
                    '-t',
                    '-i',
                    '/Users/nicola/.ssh/id_rsa',
                    'phoenix',
                    '/usr/local/bin/manage_discord.py enable && /etc/init.d/e2guardian restart || true',
                ],
                stderr=mock_subprocess.PIPE,
            ),
        ],
        any_order=True,
    )


@pytest.mark.xfail(reason='mock_os_kill.assert_called_with(15) not called')
def test_main_off(mock_os_chmod, mock_os_kill, mock_subprocess):
    main(['off'], prog_name='minecraft_ctl')
    mock_os_chmod.assert_has_calls([mock.call('/Applications/Minecraft.app/Contents/MacOS/launcher', 0)])
    mock_subprocess.assert_has_calls(
        [
            mock.call.check_output(
                [
                    'ssh',
                    '-i',
                    '/Users/nicola/.ssh/mt_remote',
                    'manage_internet@mt',
                    '/ip firewall address-list enable numbers=(10, 11)',
                ],
                stderr=mock_subprocess.PIPE,
            ),
            mock.call.check_output(
                [
                    'ssh',
                    '-t',
                    '-i',
                    '/Users/nicola/.ssh/id_rsa',
                    'phoenix',
                    '/usr/local/bin/manage_discord.py disable && /etc/init.d/e2guardian restart || true',
                ],
                stderr=mock_subprocess.PIPE,
            ),
        ],
        any_order=True,
    )
    mock_os_kill.assert_called_with(15)


def test_main_status(mock_os_chmod, mock_subprocess, monkeypatch):
    with monkeypatch.context() as m:
        mock_os_stat = mock.MagicMock(name='stat')
        mock_os_stat.side_effect = os_stat
        m.setattr('tools.bin.minecraft_ctl.os.stat', mock_os_stat)
        main(['status'], prog_name='minecraft_ctl')
    mock_os_chmod.assert_not_called()
    mock_subprocess.check_output.assert_has_calls(
        [
            mock.call(['ps', 'auxwww'], stderr=mock_subprocess.PIPE),
            mock.call(
                [
                    'ssh',
                    '-i',
                    '/Users/nicola/.ssh/mt_remote',
                    'manage_internet@mt',
                    '/ip firewall address-list print from=10,11',
                ],
                stderr=mock_subprocess.PIPE,
            ),
        ]
    )
    for launcher in DEFAULTS['minecraft_ctl']['launcher']:
        mock_os_stat.assert_has_calls([mock.call(launcher)])
    mock_subprocess.check_output.assert_has_calls([mock.call(['ps', 'auxwww'], stderr=mock_subprocess.PIPE)])
    mock_subprocess.check_output.assert_has_calls(
        [
            mock.call(
                [
                    'ssh',
                    '-i',
                    '/Users/nicola/.ssh/mt_remote',
                    'manage_internet@mt',
                    '/ip firewall address-list print from=10,11',
                ],
                stderr=mock_subprocess.PIPE,
            )
        ]
    )
