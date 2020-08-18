from unittest import mock
import pytest

from tools.libs.text_utils import CompareContents


@pytest.fixture
def difflib(monkeypatch):
    mock_difflib = mock.MagicMock(name='difflib')
    monkeypatch.setattr('tools.libs.text_utils.difflib', mock_difflib)
    yield mock_difflib


def test_CompareContents(difflib):
    cc = CompareContents('myold\line 2', 'mynew\line 2')
    print(cc)
    difflib.unified_diff.assert_called_with(['myold\\line 2'], ['mynew\\line 2'], n=1)


def test_CompareContents_filenames(difflib):
    cc = CompareContents('myold\line 2', 'mynew\line 2', 'oldfile', 'newfile')
    print(cc)
    print(difflib.mock_calls)
    difflib.unified_diff.assert_called_with(
        ['myold\\line 2'], ['mynew\\line 2'], fromfile='oldfile', tofile='newfile', n=1
    )
