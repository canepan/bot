from tools.libs import stools_defaults


def test_parse_args():
    cfg = stools_defaults.parse_args(['-v', 'test'], {'filenames': {'nargs': '+'}})
    assert cfg.verbose is True
    assert cfg.filenames == ['test']
