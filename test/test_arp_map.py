import pytest
import re
from unittest import mock

from click.testing import CliRunner

from tools.bin.arp_map import main, ArpMapRecords


@pytest.fixture(autouse=True)
def mock_netifaces(monkeypatch):
    mock_obj = mock.MagicMock(name='netifaces')
    monkeypatch.setattr('tools.bin.arp_map.netifaces', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture(autouse=True)
def mock_socket(monkeypatch):
    mock_obj = mock.MagicMock(name='socket')
    monkeypatch.setattr('tools.bin.arp_map.socket', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_subprocess(monkeypatch):
    mock_obj = mock.Mock(name='subprocess')
    mock_obj.run.return_value.stdout = '\n'.join(
        [
            'raspy2.tld.d (192.168.19.66) at 00:11:32:29:65:2e [ether] on eth0',
            '? (192.168.19.99) at <incomplete> on eth0',
            'dns.tld.d (192.168.19.53) at 00:11:32:29:65:2e [ether] on eth0',
            '? (172.24.0.2) at 02:42:ac:18:00:02 [ether] on br-bfbbcd2ade20',
        ]
    )
    monkeypatch.setattr('tools.bin.arp_map.subprocess', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


def test_main(mock_subprocess):
    runner = CliRunner()
    result = runner.invoke(main, [])
    assert result.exit_code == 0
    assert re.search(r'172\.24\.0\.2.*br-bfbbcd2ade20', result.output)
    assert '192.168.19.53' not in result.output
    assert any(re.search(r'raspy2\.tld\.d.*dns\.tld\.d', line) for line in result.output.splitlines())
    mock_subprocess.run.assert_called_with(['/usr/sbin/arp', '-a'], capture_output=True, text=1)


def test_main_eth0(mock_subprocess):
    runner = CliRunner()
    result = runner.invoke(main, ['-i', 'eth0'])
    assert result.exit_code == 0
    assert '172.24.0.2' not in result.output
    assert 'eth0' not in result.output


def test_arp_map_records(mock_subprocess):
    r = ArpMapRecords(lines=['raspy2.tld.d (192.168.19.66) at 00:11:32:29:65:2e [ether] on eth0'])
    assert next(iter(r))
    mock_subprocess.run.assert_not_called()
