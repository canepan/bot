import os
from unittest import mock

import pytest
from click.testing import CliRunner

from tools.bin.service_map import main, ServiceCatalog, ServiceConfig


def mapped_mock_open(file_contents_dict):
    """Create a mock "open" that will mock open multiple files based on name
    Args:
        file_contents_dict: A dict of 'fname': 'content'
    Returns:
        A Mock opener that will return the supplied content if name is in
        file_contents_dict, otherwise the builtin open
    """
    # builtin_open = open
    mock_files = {}
    for fname, content in file_contents_dict.items():
        mock_files[fname] = mock.mock_open(read_data=content).return_value

    def my_open(fname, *args, **kwargs):
        if fname in mock_files:
            return mock_files[fname]
        elif 'r' in args[0]:
            raise FileNotFoundError()
            # return builtin_open(fname, *args, **kwargs)
        else:
            return mock.mock_open().return_value

    mock_opener = mock.Mock(name='opener')
    mock_opener.side_effect = my_open
    return mock_opener


@pytest.fixture
def mock_ip_if_not_local(monkeypatch):
    mock_obj = mock.Mock(name='ip_if_not_local')
    mock_obj.check_output.side_effect = ['127.0.0.1', '127.0.0.1', None]
    monkeypatch.setattr('tools.bin.service_map.ip_if_not_local', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_open(monkeypatch):
    mock_obj = mapped_mock_open(
        {
            'base_dir.d/aaa.conf': '# {"vrrp": ["phoenix"]}\nvrrp_instance aaa {\n state MASTER}',
            'base_dir.d/foobar.conf': '# {"vrrp": ["raspy2"]}\nvrrp_instance foobar {\n state MASTER}',
            'base_dir.d/zzz.conf': '# {"vrrp": ["other"]}\nvrrp_instance zzz {\n state MASTER}',
            'base_dir/keepalived.conf': '# {"vrrp": ["myhost", "other"]}\n\nvrrp_script chk_dns {\n   script '
            '"/etc/keepalived/bin/check_dns.sh"\n   interval 60\n   weight -100\n}\n\nvrrp_instance DNS {\n   state '
            'BACKUP\n   interface eth0\n   virtual_router_id 222\n   priority 80\n   virtual_ipaddress {\n      '
            '192.168.19.222/24 dev eth0\n   }\n   track_script {\n       chk_dns\n    }\n    notify '
            '/etc/keepalived/bin/kanotify.sh\n}\n',
        }
    )
    monkeypatch.setattr('builtins.open', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_subprocess(monkeypatch):
    mock_obj = mock.Mock(name='subprocess')
    mock_obj.check_output.return_value.decode.return_value = 'my_content'
    monkeypatch.setattr('tools.bin.service_map.subprocess', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_walk(monkeypatch):
    mock_obj = mock.Mock(name='os.walk')
    mock_obj.return_value = [['base_dir.d', [], ['aaa.conf', 'foobar.conf', 'zzz.conf']]]
    monkeypatch.setattr('tools.bin.service_map.os.walk', mock_obj)
    yield mock_obj
    print(f'{mock_obj} calls: {mock_obj.mock_calls}')


def test_ServiceCatalog(mock_ip_if_not_local, mock_open, mock_subprocess, mock_walk):
    sc = ServiceCatalog('/etc/keepalived/keepalived.d', mock.Mock(name='log'))
    assert sc.services == {
        'aaa': ['phoenix'],
        'foobar': ['raspy2'],
        'zzz': ['other'],
        'keepalived': ['phoenix', 'raspy2', 'other'],
    }
    assert sc.hosts == {
        'phoenix': {ServiceConfig('phoenix', 'aaa'), ServiceConfig('phoenix', 'keepalived')},
        'raspy2': {ServiceConfig('raspy2', 'foobar'), ServiceConfig('raspy2', 'keepalived')},
        'other': {ServiceConfig('other', 'zzz'), ServiceConfig('other', 'keepalived')},
    }
    mock_open.assert_called_with('base_dir.d/zzz.conf', 'r')


def test_ServiceConfig(mock_ip_if_not_local, mock_open, mock_subprocess, mock_walk):
    sc = ServiceConfig('testhost', 'keepalived')
    assert sc['base_dir/testfile.conf'] == 'my_content'
    mock_subprocess.check_output.assert_called_with(['ssh', 'testhost', 'cat', 'base_dir/testfile.conf'])


def test_main(mock_open, mock_subprocess, mock_walk):
    runner = CliRunner()
    result = runner.invoke(main, ['--ka-dir', os.path.join(os.path.dirname(__file__), 'fixtures', 'ka_dir')])
    assert result.exit_code == 0
    expected = '\n'.join(
        [
            '{',
            '  "keepalived": [',
            '    "phoenix",',
            '    "raspy2",',
            '    "other"',
            '  ],',
            '  "aaa": [',
            '    "phoenix"',
            '  ],',
            '  "foobar": [',
            '    "raspy2"',
            '  ],',
            '  "zzz": [',
            '    "other"',
            '  ]',
            '}\n',
        ]
    )
    assert result.output == expected
