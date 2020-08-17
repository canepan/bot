import configargparse
import sys

from . import logging_utils


class LoggingArgumentParser(configargparse.ArgumentParser):
    def __init__(self, *args, app_name: str = None, **kwargs):
        super(LoggingArgumentParser, self).__init__(*args, **kwargs)
        self.add_argument('--config', '-c', is_config_file=True, help='{} config file'.format(app_name))
        g = self.add_mutually_exclusive_group()
        g.add_argument('-q', '--quiet', action='store_true')
        g.add_argument('-v', '--verbose', action='store_true')
        self.app_name = app_name

    def parse_args(self, *args, **kwargs):
        cfg = super(LoggingArgumentParser, self).parse_args(*args, **kwargs)
        cfg.log = logging_utils.get_logger(self.app_name, verbose=cfg.verbose, quiet=cfg.quiet)
        return cfg


def arg_parser(description: str) -> configargparse.ArgumentParser:
    parser = configargparse.ArgumentParser(
        description=description,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    return parser


def with_quiet_verbose(
    app_name: str, parser: configargparse.ArgumentParser = None, argv: list = None, logfile: str = None
) -> configargparse.Namespace:
    """
    Optionally create a parser, add --quiet/--verbose and return parsed args with `.log`
    """
    if not parser:
        parser = arg_parser(description='{} arguments'.format(app_name))
    parser.add_argument('--config', '-c', is_config_file=True, help='{} config file'.format(app_name))
    g = parser.add_mutually_exclusive_group()
    g.add_argument('-q', '--quiet', action='store_true')
    g.add_argument('-v', '--verbose', action='store_true')
    if argv is None:
        argv = sys.argv[1:]
    cfg = parser.parse_args(argv)
    cfg.log = logging_utils.get_logger(
        app_name, verbose=cfg.verbose, quiet=cfg.quiet, with_file=logfile.format(**cfg.__dict__)
    )
    return cfg

