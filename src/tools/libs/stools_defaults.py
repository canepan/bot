import argparse
import sys

from .parse_args import LoggingArgumentParser


APP_NAME = 'canepan.tools'
HOSTS = ['phoenix', 'raspy2', 'raspy3']


def parse_args(argv=sys.argv[1:], descr='Sync local to remote files with the same name') -> argparse.Namespace:
    parser = LoggingArgumentParser(description=descr, app_name=APP_NAME)
    parser.add_argument('--diff', '-d', default='diff -buB', help='Command (with params) to use for diff')
    parser.add_argument('--hosts', '-H', nargs='+', default=HOSTS)
    parser.add_argument('filenames', nargs='+')
    cfg = parser.parse_args(argv)
    return cfg
