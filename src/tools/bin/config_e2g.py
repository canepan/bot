#!/mnt/opt/nicola/tools/bin/python3
import argparse
import attr
import json
import logging
import os
import re
import sys
from datetime import datetime

from tools.lib.logging_utils import MaxLevelFilter


APP_NAME = 'canepa.e2g.config'
ETC_DIR = '/etc/e2guardian'

_log = logging.getLogger(APP_NAME)


def parse_args(argv=None, descr='Create e2g configuration') -> argparse.Namespace:
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(
        description=descr,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('categories', nargs='+', default=['adult', 'games'], help='Categories to ban')
    parser.add_argument('--filenames', nargs='+', default=['banned', 'weighted'], help='Base names to append sitelist and urllist to')
    parser.add_argument(
        '--rules-dir', '-r', default='kids', help='Directory with the rules files (relative to )'.format(ETC_DIR)
    )
    parser.add_argument('--unsafe', action='store_true', help='Really write/rename files')
    g = parser.add_mutually_exclusive_group()
    g.add_argument('-q', '--quiet', action='store_true')
    g.add_argument('-v', '--verbose', action='store_true')
    cfg = parser.parse_args(argv)
    cfg.log = logging.getLogger(APP_NAME)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.INFO)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.addFilter(MaxLevelFilter(logging.INFO))
    cfg.log.addHandler(stderr_handler)
    cfg.log.addHandler(stdout_handler)
    if cfg.verbose:
        cfg.log.setLevel(logging.DEBUG)
    elif cfg.quiet:
        cfg.log.setLevel(logging.ERROR)
    else:
        cfg.log.setLevel(logging.INFO)
    return cfg


def file_content(filename):
    with open(filename) as f:
        return f.read()


@attr.s
class Category(object):
    category_map = {'sitelist': 'domains', 'urllist': 'urls', 'phraselist': 'weighted'}
    list_map = {'sitelist': 'blacklists', 'urllist': 'blacklists', 'phraselist': 'phraselists'}
    FILE_HEADER = {
        'sitelist': '.Include</etc/e2guardian/kids/bannedtimes>\n',
        'urllist': '.Include</etc/e2guardian/kids/bannedtimes>\n',
        'phraselist': '.Include</etc/e2guardian/kids/bannedtimes>\n',
    }
    FILE_FOOTER = {'sitelist': '', 'urllist': '', 'phraselist': ''}
    category = attr.ib()

    def _list_file(self, category_type):
        return f'{ETC_DIR}/lists/{self.list_map[category_type]}/{self.category}/{self.category_map[category_type]}'

    def line(self, category_type):
        return f'.Include<{self._list_file(category_type)}>'

    @classmethod
    def rules_file(cls, filename, category_type, rules_dir):
        return os.path.join(ETC_DIR, rules_dir, '{}{}'.format(filename, category_type))

    def exists(self, category_type):
        catfile = self._list_file(category_type)
        _log.debug('Checking list %s', catfile)
        return os.path.isfile(catfile)


def e2config_exists(category_type: str, rules_dir: str, basename: str) -> bool:
    fname = os.path.join(ETC_DIR, rules_dir, '{}{}'.format(basename, category_type))
    _log.debug('Checking config %s', fname)
    return os.path.isfile(fname)


def main():
    cfg = parse_args()
    categories = [Category(c) for c in cfg.categories]
    for fn in cfg.filenames:
        for ctype in (c for c in ('sitelist', 'urllist', 'phraselist') if e2config_exists(c, cfg.rules_dir, fn)):
            new_config = '{}{}{}'.format(
                Category.FILE_HEADER[ctype],
                '\n'.join([category.line(ctype) for category in categories if category.exists(ctype)]),
                Category.FILE_FOOTER[ctype],
            )
            _log.debug(new_config)
            rules_file = Category.rules_file(fn, ctype, cfg.rules_dir)
            if new_config.strip() != file_content(rules_file).strip():
                _log.info('Rules for %s/%s differ: replacing', fn, ctype)
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                if cfg.unsafe:
                    _log.info(
                        'Renaming %s to %s', rules_file,
                        '{}.{}'.format(rules_file, timestamp)
                    )
                    os.rename(rules_file, '{}.{}'.format(rules_file, timestamp))
                    with open(rules_file, 'w') as f:
                        _log.info('Writing new %s', rules_file)
                        f.write(new_config)
                else:
                    _log.info('Would rename %s to %s', rules_file, '{}.{}'.format(rules_file, timestamp))
                    _log.info('Would have rewritten %s', rules_file)
            else:
                _log.info('Rules in %s are the same: keeping', rules_file)
    return 0


if __name__ == '__main__':
    sys.exit(main())

