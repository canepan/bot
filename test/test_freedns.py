import pytest

from tools.bin import freedns


def test_parse_args():
    with pytest.raises(SystemExit) as exc_info:
        freedns.parse_args([])
    print(exc_info)
    assert exc_info.value.args == (2,)
