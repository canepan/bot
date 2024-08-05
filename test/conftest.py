import pytest
from unittest import mock


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
def mock_os(monkeypatch):
    mock_obj = mock.MagicMock(name='os')
    mock_obj.path.expanduser.side_effect = lambda x: x.replace('~', 'HOME')
    monkeypatch.setattr('tools.bin.backup_mysql.os', mock_obj)
    monkeypatch.setattr('tools.bin.id3checker.os', mock_obj)
    monkeypatch.setattr('tools.bin.nwn.os', mock_obj)
    monkeypatch.setattr('tools.bin.openvpn_log.os', mock_obj)
    yield mock_obj
    print(f'{mock_obj}: {mock_obj.mock_calls}')
