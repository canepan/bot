import traceback
from unittest import mock

import pytest
from click.testing import CliRunner

from tools.bin.id3checker import main


@pytest.fixture
def mock_eyed3(monkeypatch):
    mock_obj = mock.MagicMock(name='eyed3')
    mock_obj.load.return_value.tag = mock.Mock(name="song.tag", artist="artist", album="album", track_num=[1, 5])
    monkeypatch.setattr('tools.bin.id3checker.eyed3', mock_obj)
    yield mock_obj
    print(f'{mock_obj} {mock_obj.mock_calls}')


def test_main(mock_eyed3, mock_os):
    runner = CliRunner()
    mock_os.walk.return_value = (("songs_dir", None, ["file1", "file2", "file3"]),)
    result = runner.invoke(main, ["songs_dir"])
    traceback.print_exception(*result.exc_info)
    if result.exc_info:
        assert result.output != ""
    assert result.exit_code == 0, str(result)
