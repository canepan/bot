import logging
import pytest

from tools.bin import config_proxy

def test_parse_args():
    # test defaults
    cfg = config_proxy.parse_args([])
    assert cfg.verbose is False
    assert cfg.quiet is False
    assert cfg.filter_types == ['banned', 'weighted']
    assert cfg.categories == ['adult', 'games']
    assert cfg.rules_dir == 'kids'
    with pytest.raises(SystemExit):
        cfg = config_proxy.parse_args(['-v', '-q', 'other', 'that'])
    cfg = config_proxy.parse_args(['-v'])
    assert cfg.verbose is True
    assert cfg.log.isEnabledFor(logging.DEBUG)
    cfg = config_proxy.parse_args(['-q'])
    assert cfg.quiet is True
    assert not cfg.log.isEnabledFor(logging.INFO)

