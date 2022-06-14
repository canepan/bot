import os
import pytest
from unittest import mock

from tools.bin.service_map import main


def mapped_mock_open(file_contents_dict):
    """Create a mock "open" that will mock open multiple files based on name
    Args:
        file_contents_dict: A dict of 'fname': 'content'
    Returns:
        A Mock opener that will return the supplied content if name is in
        file_contents_dict, otherwise the builtin open
    """
    builtin_open = open
    mock_files = {}
    for fname, content in file_contents_dict.items():
        mock_files[fname] = mock.mock_open(read_data=content).return_value

    def my_open(fname, *args, **kwargs):
        if fname in mock_files:
            return mock_files[fname]
        else:
            return builtin_open(fname, *args, **kwargs)

    mock_opener = mock.Mock(name='opener')
    mock_opener.side_effect = my_open
    return mock_opener


@pytest.fixture
def mock_open(monkeypatch):
    mock_obj = mapped_mock_open(
        {
            'base_dir/aaa.conf': '# {"vrrp": ["phoenix"]}\nvrrp_instance smtp {\n state MASTER}',
            'base_dir/foobar.conf': '# {"vrrp": ["raspy2"]}\nvrrp_instance smtp {\n state MASTER}',
            'base_dir/zzz.conf': '# {"vrrp": ["other"]}\nvrrp_instance smtp {\n state MASTER}',
        }
    )
    monkeypatch.setattr('builtins.open', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_check_output(monkeypatch):
    mock_obj = mock.Mock(name='check_output')
    monkeypatch.setattr('tools.bin.service_map.check_output', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_walk(monkeypatch):
    mock_obj = mock.Mock(name='os.walk')
    mock_obj.return_value = [['base_dir', [], ['aaa.conf', 'foobar.conf', 'zzz.conf']]]
    monkeypatch.setattr('tools.bin.service_map.os.walk', mock_obj)
    yield mock_obj
    print(f'{mock_obj} calls: {mock_obj.mock_calls}')


def test_main(mock_open, mock_walk):
    main(['--ka-dir', os.path.join(os.path.dirname(__file__), 'fixtures', 'ka_dir')])
