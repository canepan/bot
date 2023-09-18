import click
import pytest
from unittest import mock

from click.testing import CliRunner
from conftest import mapped_mock_open
from tools.bin.simple_service_map import main, show_services, status_cache


def my_check_output(*args, **kwargs):
    if args[0][0] == "ping":
        if args[0][-1] != "phoenix":
            raise Exception(args, kwargs)
    if args[0][0] == "bash":
        if "AAA.state" in args[0][-1]:
            return "now - MASTER - ggg"
    return 'my_content'


@pytest.fixture
def mock_check_output(monkeypatch):
    mock_obj = mock.Mock(name='check_output')
    mock_obj.side_effect = my_check_output
    monkeypatch.setattr('tools.bin.simple_service_map.check_output', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_glob(monkeypatch):
    mock_obj = mock.Mock(name='glob')
    mock_obj.return_value = [
        '/etc/keepalived/keepalived.d/aaa.conf',
        '/etc/keepalived/keepalived.d/foobar.conf',
        '/etc/keepalived/keepalived.d/zzz.conf',
    ]
    monkeypatch.setattr('tools.bin.simple_service_map.glob', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_ip_if_not_local(monkeypatch):
    mock_obj = mock.Mock(name='ip_if_not_local')
    mock_obj.check_output.side_effect = ['127.0.0.1', '127.0.0.1', None]
    monkeypatch.setattr('tools.bin.simple_service_map.ip_if_not_local', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_open(monkeypatch):
    mock_obj = mapped_mock_open(
        {
            '/etc/keepalived/keepalived.d/aaa.conf': '# {"vrrp": ["phoenix"]}\nvrrp_instance AAA {\n state MASTER}',
            '/etc/keepalived/keepalived.d/foobar.conf': '# {"vrrp": ["raspy2"]}\nvrrp_instance foobar {\n}',
            '/etc/keepalived/keepalived.d/zzz.conf': '# {"vrrp": ["other", "phoenix"]}\nvrrp_instance zzz {',
        }
    )
    monkeypatch.setattr('builtins.open', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_os_path_exists(monkeypatch):
    mock_obj = mock.Mock(name='os.path.exists')
    monkeypatch.setattr('tools.bin.simple_service_map.os.path.exists', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.mark.parametrize(
    "input_dict,output_dict",
    (
        ({}, []),
        ({"host": ["s1"]}, [f"{click.style('s1', 'white', bold=True)}: host"]),
    ),
)
def test_show_services(input_dict, output_dict):
    status_cache.clear()
    assert list(show_services(input_dict)) == output_dict


def test_main(mock_open, mock_check_output, mock_glob, mock_os_path_exists):
    status_cache.clear()
    runner = CliRunner()
    result = runner.invoke(main, [])
    assert result.exit_code == 0
    assert result.output == "phoenix: +AAA, zzz\n"


def test_main_per_service(mock_open, mock_check_output, mock_glob, mock_os_path_exists):
    status_cache.clear()
    runner = CliRunner()
    result = runner.invoke(main, ["-s"])
    assert result.exit_code == 0
    assert result.output == "AAA: +phoenix\nzzz: phoenix\n"
