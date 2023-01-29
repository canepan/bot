import pytest
from unittest import mock

from tools.bin import openvpn_log


@pytest.fixture
def mock_open(monkeypatch):
    mock_obj = mock.mock_open(read_data='line1\nline2\nline with /sbin/ip test')
    monkeypatch.setattr('builtins.open', mock_obj)
    yield mock_obj
    print(f'{mock_obj}: {mock_obj.mock_calls}')


def test_main(mock_open, mock_os):
    mock_os.path.isfile.return_value = True
    assert openvpn_log.main(['my.log']) == 0
    mock_open.assert_called_with('my.log', 'r')


def test_main_missing_file(mock_open, mock_os):
    mock_os.path.isfile.return_value = False
    assert openvpn_log.main(['my.log']) == 1
    mock_open.assert_not_called()
