import pytest

from tools.lib import stools_defaults

def test_parse_args():
    cfg = stools_defaults.parse_args(['-v', 'test'])
    assert cfg.verbose is True
    assert cfg.filenames == ['test']
