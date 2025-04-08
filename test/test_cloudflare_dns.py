from unittest import mock

import pytest
from click.testing import CliRunner

from tools.bin.cloudflare_dns import main


@pytest.fixture
def mock_requests(monkeypatch):
    mock_obj = mock.MagicMock(name='requests')
    mock_obj.get.return_value.json.return_value = {
        'result': [
            {
                "zone_id": "XXX",
                "id": "IDAUTH",
                "name": "www.mydomain",
                "type": "A",
                'proxied': True,
                'ttl': 1,
                "content": "10.11.12.33",
            }
        ],
        'success': True,
    }
    monkeypatch.setattr('tools.bin.cloudflare_dns.requests', mock_obj)
    yield mock_obj
    print(f'{mock_obj} calls: {mock_obj.mock_calls}')


@pytest.fixture
def mock_my_zones(monkeypatch):
    mock_obj = mock.MagicMock(name='my_zones')
    mock_obj = {
        "mydomain": {
            "id": "XXX",
            "token": "YYY",
            "www.mydomain": {"id": "ZZZ", "type": "A", "name": "www.mydomain", "proxied": True, "ttl": 1},
        }
    }
    monkeypatch.setattr('tools.bin.cloudflare_dns.MY_ZONES', mock_obj)
    yield mock_obj


@pytest.fixture(autouse=True)
def mock_open(monkeypatch):
    domain = "nicolacanepa.net"
    mock_cfg = f'''{{
        "{domain}": {{
            "id": "NNN",
            "token": "CCC",
            "www.{domain}": {{"id": "UUU", "type": "A", "name": "www.{domain}", "proxied": true, "ttl": 1}}
        }}
    }}'''
    mock_obj = mock.mock_open(read_data=mock_cfg)
    monkeypatch.setattr('builtins.open', mock_obj)
    yield mock_obj
    print(f'{mock_obj}: {mock_obj.mock_calls}')


def test_list(mock_requests, mock_my_zones):
    runner = CliRunner()
    result = runner.invoke(main, ['--zone', 'mydomain', 'list'])
    assert result.exit_code == 0
    mock_requests.get.assert_called_with(
        'https://api.cloudflare.com/client/v4/zones/XXX/dns_records',
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer YYY'},
    )


def test_list_default(mock_requests, mock_my_zones):
    runner = CliRunner()
    result = runner.invoke(main, ['list'])
    assert result.exit_code == 0
    mock_requests.get.assert_called_with(
        'https://api.cloudflare.com/client/v4/zones/NNN/dns_records',
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer CCC'},
    )


def test_list_unknown_domain(mock_requests, mock_my_zones):
    runner = CliRunner()
    result = runner.invoke(main, ['--zone', 'otherdomain', 'list'])
    assert result.exit_code == 0
    mock_requests.get.assert_called_with(
        'https://api.cloudflare.com/client/v4/zones/None/dns_records',
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer None'},
    )


def test_update(mock_requests, mock_my_zones):
    runner = CliRunner()
    result = runner.invoke(main, ['-v', '--zone', 'mydomain', 'update', '10.11.12.13'])
    assert result.exit_code == 0
    mock_requests.put.assert_not_called()


def test_update_unsafe(mock_requests, mock_my_zones):
    runner = CliRunner()
    result = runner.invoke(main, ['--zone', 'mydomain', 'update', '--unsafe', '10.11.12.13'])
    assert result.exit_code == 0
    mock_requests.put.assert_called_with(
        'https://api.cloudflare.com/client/v4/zones/XXX/dns_records/IDAUTH',
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer YYY'},
        json={
            'zone_id': 'XXX',
            'id': 'IDAUTH',
            'type': 'A',
            'name': 'www.mydomain',
            'proxied': True,
            'ttl': 1,
            'content': '10.11.12.13',
        },
    )
