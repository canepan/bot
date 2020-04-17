import pytest

from tools.bin import config_e2g

def test_parse_args():
    cfg = config_e2g.parse_args(['-v', 'test'])
    assert cfg.verbose is True
    assert cfg.filenames == ['banned', 'weighted']
    assert cfg.categories == ['test']
    with pytest.raises(SystemExit):
        cfg = config_e2g.parse_args(['-v', '-q', 'other', 'that'])

