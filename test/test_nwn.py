from unittest import mock
import pytest

from tools.bin.nwn import main


@pytest.fixture
def mock_subprocess(monkeypatch):
    mock_obj = mock.MagicMock(name='subprocess')
    monkeypatch.setattr('tools.bin.nwn.subprocess', mock_obj)
    yield mock_obj


def test_nwn(mock_os, mock_subprocess):
    def dir_exists(dirname) -> bool:
        print(f'{dirname}: {dir_map[dirname]}')
        return dir_map[dirname]

    main(['on'])
    dir_map = {
        'HOME/Documents/Nicola/Mac': True,
        'HOME/Documents/Neverwinter Nights': False,
    }
    mock_os.isdir.side_effect = dir_exists
    base_dir = 'HOME/Documents/Nicola'
    mock_subprocess.run.assert_has_calls(
        [
            mock.call(
                [
                    'hdiutil',
                    'mount',
                    f'{base_dir}/NWNConfig.sparseimage',
                    '-mountpoint',
                    'HOME/Documents/Neverwinter Nights',
                ],
                stdout=mock_subprocess.PIPE,
                stderr=mock_subprocess.PIPE,
            ),
        ]
    )
    mock_subprocess.run.assert_has_calls(
        [
            mock.call(
                ['ssh', '-o', 'ConnectTimeout 2', '-q', 'quark', 'hostname'],
                stdout=mock_subprocess.PIPE,
                stderr=mock_subprocess.PIPE,
            ),
        ]
    )
    mock_subprocess.run.assert_has_calls(
        [
            mock.call(
                ['hdiutil', 'mount', f'{base_dir}/NicolaMac.dmg', '-mountpoint', f'{base_dir}/Mac'],
                stdout=mock_subprocess.PIPE,
                stderr=mock_subprocess.PIPE,
            ),
        ]
    )
    mock_subprocess.run.assert_has_calls(
        [
            mock.call(
                [f'{base_dir}/Mac/Neverwinter Nights Enhanced Edition/bin/macos/nwmain.app/Contents/MacOS/nwmain'],
                stdout=mock_subprocess.PIPE,
                stderr=mock_subprocess.PIPE,
            ),
        ]
    )
    mock_os.rmdir.assert_has_calls(
        [
            mock.call(f'{base_dir}/Mac'),
        ]
    )
    mock_os.rmdir.assert_has_calls(
        [
            mock.call('HOME/Documents/Neverwinter Nights'),
        ]
    )
