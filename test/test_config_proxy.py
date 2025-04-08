import logging

import pytest

from tools.bin import config_proxy


def test_parse_args_defaults():
    # test defaults
    cfg = config_proxy.parse_args([])
    assert cfg.verbose is False
    assert cfg.quiet is False
    assert cfg.filter_types == ['banned', 'weighted']
    assert cfg.categories == ['adult', 'games']
    assert cfg.rules_dir == 'kids'
    for handler in [h for h in cfg.log.handlers if h.get_name() in ('stderr', 'stdout')]:
        cfg.log.removeHandler(handler)


def test_parse_args_conflicting():
    with pytest.raises(SystemExit):
        config_proxy.parse_args(['-v', '-q', 'other', 'that'])


def test_parse_args_verbose():
    cfg = config_proxy.parse_args(['-v'])
    assert cfg.verbose is True
    assert cfg.log.isEnabledFor(logging.DEBUG)
    for handler in [h for h in cfg.log.handlers if h.get_name() in ('stderr', 'stdout')]:
        cfg.log.removeHandler(handler)


def test_parse_args_quiet():
    cfg = config_proxy.parse_args(['-q'])
    assert cfg.quiet is True
    logging.LogRecord('name', logging.INFO, '/', 0, 'test', [], None)
    # this doesn't work after adding support for logfile
    # for handler in cfg.log.handlers:
    #     print('{}: {}'.format(handler, handler.name))
    # assert not cfg.log.isEnabledFor(logging.INFO)
    # for handler in cfg.log.handlers:
    #     assert handler.filter(record)
    for handler in [h for h in cfg.log.handlers if h.get_name() in ('stderr', 'stdout')]:
        cfg.log.removeHandler(handler)
