import click
import os
import pytest
from unittest import mock

from click.testing import CliRunner
from conftest import mapped_mock_open
from tools.bin.simple_service_map import main, show_services, Host


def my_check_output(*args, **kwargs):
    if args[0][0] == "ping":
        if args[0][-1] == "other":
            raise Exception(args, kwargs)
    if args[0][0:2] == ["bash", "-c"]:
        if "AAA.state" in args[0][-1]:
            return "now - MASTER - INSTANCE"
    if args[0][2].startswith("ip ") or args[0][4].startswith("ip "):
        return "\n".join(
            [
                "2: eth0    inet 192.168.19.25/24 scope global secondary eth0\\     valid_lft forever "
                "preferred_lft forever",
                "2: eth0    inet 192.168.19.63/24 scope global secondary eth0\\     valid_lft forever "
                "preferred_lft forever",
                "2: eth0    inet 192.168.19.222/24 scope global secondary eth0\\     valid_lft forever "
                "preferred_lft forever",
                "2: eth0    inet 192.168.19.59/24 scope global secondary eth0\\     valid_lft forever "
                "preferred_lft forever",
            ]
        )
    return '20240226084734 - BACKUP - INSTANCE'


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
    resolve_dict = {"phoenix": None, "raspy2": "127.0.0.1", "other": "127.0.0.2"}
    mock_obj.side_effect = resolve_dict.get
    monkeypatch.setattr('tools.bin.simple_service_map.ip_if_not_local', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_open(monkeypatch):
    mock_obj = mapped_mock_open(
        {
            '/etc/keepalived/keepalived.d/aaa.conf': '# {"vrrp": ["phoenix"]}\n'
            'vrrp_instance AAA {\n  state MASTER\n  virtual_router_id 222\n',
            '/etc/keepalived/keepalived.d/foobar.conf': '# {"vrrp": ["other"]}\nvrrp_instance foobar {\n}',
            '/etc/keepalived/keepalived.d/zzz.conf': '# {"vrrp": ["raspy2", "phoenix"]}\nvrrp_instance zzz {\n'
            '  virtual_router_id 222\n  virtual_ipaddress {\n    192.168.19.222/24 dev eth0\n  }\n}',
        }
    )
    monkeypatch.setattr('builtins.open', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_os(monkeypatch):
    mock_obj = mock.Mock(name='mock_os')
    mock_obj.path.basename = os.path.basename
    mock_obj.path.join = os.path.join
    monkeypatch.setattr('tools.bin.simple_service_map.os', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.mark.parametrize(
    "input_dict,output_list",
    (
        ({}, []),
        ({"host": ["s1"]}, [f"{click.style('s1', 'white', bold=True)}: host", "Legend: running"]),
    ),
)
def test_show_services(input_dict, output_list):
    Host.status_cache.clear()
    assert list(show_services(input_dict)) == output_list


def test_main(mock_open, mock_check_output, mock_glob, mock_ip_if_not_local, mock_os):
    Host.status_cache.clear()
    runner = CliRunner()
    result = runner.invoke(main, [])
    if result.exception:
        raise result.exception
    assert result.output == "phoenix: -AAA, zzz\nLegend: +active, running\n"
    assert result.exit_code == 0


def test_main_per_service(mock_open, mock_check_output, mock_glob, mock_ip_if_not_local, mock_os):
    Host.status_cache.clear()
    runner = CliRunner()
    result = runner.invoke(main, ["-s"])
    if result.exception:
        raise result.exception
    assert result.output == "AAA: -phoenix\nzzz: phoenix\nLegend: +active, running\n"
    assert result.exit_code == 0
