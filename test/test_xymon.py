from unittest import mock

import pytest

from tools.libs.xymon import Xymon, XymonStatus


@pytest.fixture
def mock_check_output(monkeypatch):
    mock_obj = mock.Mock(name='check_output')
    monkeypatch.setattr('tools.libs.xymon.check_output', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_socket(monkeypatch):
    mock_obj = mock.Mock(name='socket')
    mock_obj.getfqdn.return_value = "my.fqdn.tld"
    monkeypatch.setattr('tools.libs.xymon.socket', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.fixture
def mock_time(monkeypatch):
    mock_obj = mock.Mock(name='time')
    monkeypatch.setattr('tools.libs.xymon.time', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


@pytest.mark.parametrize(
    "status,message",
    ((XymonStatus.GREEN, "All OK"), (XymonStatus.YELLOW, "Not great"), (XymonStatus.RED, "The end is nigh")),
)
def test_xymon(mock_check_output, mock_os, mock_socket, mock_time, status, message):
    x = Xymon(mock.Mock(name="cfg", debug=False), "test_app", "my_check_name")
    x.send_status(status, message)
    text = f"status my,fqdn,tld.my_check_name {status.value} {mock_time.asctime.return_value}\n{message}"
    mock_check_output.assert_called_with(["xymon", "192.168.0.68", text])


def test_xymon_debug(mock_check_output, mock_os, mock_socket, mock_time):
    x = Xymon(mock.Mock(name="cfg", debug=True), "test_app", "my_check_name")
    x.send_status(XymonStatus.GREEN, "OK")
    text = f"status my,fqdn,tld.my_check_name green {mock_time.asctime.return_value}\nOK"
    mock_check_output.assert_called_with(["echo", "xymon", "192.168.0.68", text])
