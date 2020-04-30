#!/mnt/opt/nicola/tools/bin/python3
import configargparse
import attr
import json
import logging
import os
import re
import sys
from datetime import datetime

from tools.lib import (logging_utils, text_utils)


APP_NAME = 'canepa.e2g.config'
ETC_DIR = '/etc/e2guardian'

_log = logging.getLogger('tools')


def parse_args(argv: list, descr='Create e2g configuration') -> configargparse.Namespace:
    parser = configargparse.ArgumentParser(
        description=descr,
        formatter_class=configargparse.ArgumentDefaultsHelpFormatter,
        default_config_files=[],
    )
    parser.add_argument('--categories', nargs='+', default=['adult', 'games'], help='Categories to ban')
    parser.add_argument('--config', '-c', is_config_file=True, help='{} config file'.format(APP_NAME))
    parser.add_argument('--filenames', nargs='+', default=['banned', 'weighted'], help='Base names to append sitelist and urllist to')
    parser.add_argument(
        '--rules-dir', '-r', default='kids', help='Directory with the rules files (relative to )'.format(ETC_DIR)
    )
    parser.add_argument('--unsafe', action='store_true', help='Really write/rename files')
    g = parser.add_mutually_exclusive_group()
    g.add_argument('-q', '--quiet', action='store_true')
    g.add_argument('-v', '--verbose', action='store_true')
    cfg = parser.parse_args(argv)
    cfg.log = logging_utils.get_logger('tools', verbose=cfg.verbose, quiet=cfg.quiet)
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
        return os.path.isfile(catfile)


def e2config_exists(category_type: str, rules_dir: str, basename: str) -> bool:
    fname = os.path.join(ETC_DIR, rules_dir, '{}{}'.format(basename, category_type))
    _log.debug('Checking config %s', fname)
    return os.path.isfile(fname)


def main(argv=sys.argv[1:]):
    cfg = parse_args(argv)
    categories = [Category(c) for c in cfg.categories]
    cfg.log.info('About to ban %s', cfg.categories)
    changed_files = 0
    for fn in cfg.filenames:
        for ctype in (c for c in ('sitelist', 'urllist', 'phraselist') if e2config_exists(c, cfg.rules_dir, fn)):
            new_config = '{}{}{}'.format(
                Category.FILE_HEADER[ctype],
                '\n'.join([category.line(ctype) for category in categories if category.exists(ctype)]),
                Category.FILE_FOOTER[ctype],
            )
            rules_file = Category.rules_file(fn, ctype, cfg.rules_dir)
            current_config = file_content(rules_file)
            if new_config.strip() != current_config.strip():
                changed_files += 1
                _log.info('Rules for %s/%s differ: replacing', fn, ctype)
                _log.debug('Full difference:\n%s', text_utils.CompareContents(
                    current_config, new_config,
                    old_file_name=f'current {rules_file}', new_file_name=f'proposed {rules_file}'
                ))
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
    if changed_files == 0:
        _log.error('No files to change')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

