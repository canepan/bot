#!/mnt/opt/nicola/tools/bin/python3
import argparse
import attr
import json
import logging
import os
import re
import sys
from datetime import datetime


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
    parser.add_argument('--filenames', nargs='+', default=['banned'], help='Base names to append sitelist and urllist to')
    parser.add_argument(
        '--rules-dir', '-r', default='kids', help='Directory with the rules files (relative to )'.format(ETC_DIR)
    )
    parser.add_argument('--unsafe', action='store_true', help='Really write/rename files')
    g = parser.add_mutually_exclusive_group()
    g.add_argument('-q', '--quiet', action='store_true')
    g.add_argument('-v', '--verbose', action='store_true')
    cfg = parser.parse_args(argv)
    cfg.log = logging.getLogger(APP_NAME)
    if cfg.verbose:
        cfg.log.setLevel('DEBUG')
        cfg.log.addHandler(logging.StreamHandler())
    elif cfg.quiet:
        cfg.log.setLevel('ERROR')
    return cfg


def file_content(filename):
    with open(filename) as f:
        return f.read()


@attr.s
class Category(object):
    category_mapping = {'sitelist': 'domains', 'urllist': 'urls'}
    FILE_HEADER = {
        'sitelist': '.Include</etc/e2guardian/kids/bannedtimes>\n',
        'urllist': '.Include</etc/e2guardian/kids/bannedtimes>\n',
    }
    FILE_FOOTER = {'sitelist': '', 'urllist': ''}
    category = attr.ib()
    rules_dir = attr.ib()

    def line(self, category_type):
        return f'#.Include<{ETC_DIR}/lists/blacklists/{self.category}/{self.category_mapping[category_type]}>'

    @classmethod
    def rules_file(cls, filename, category_type, rules_dir):
        return os.path.join(ETC_DIR, rules_dir, '{}{}'.format(filename, category_type))

    @classmethod
    def exists(cls, catname):
        basedir = os.path.join(ETC_DIR, 'lists', 'blacklists')
        domfile = os.path.join(basedir, catname, 'domains')
        urlfile = os.path.join(basedir, catname, 'urls')
        return os.path.isfile(domfile) and os.path.isfile(urlfile)


def main():
    cfg = parse_args()
    categories = (Category(c) for c in cfg.categories if Category.exists(c))
    for fn in cfg.filenames:
        for ctype in ('sitelist', 'urllist'):
            new_config = '{}{}{}'.format(
                Category.FILE_HEADER[ctype],
                '\n'.join([category.line(ctype) for category in categories]),
                Category.FILE_FOOTER[ctype],
            )
            rules_file = Category.rules_file(fn, ctype, cfg.rules_dir)
            if new_config.strip() != file_content(rules_file).strip():
                _log.info('Rules for %s/%s differ: replacing', fn, ctype)
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                if cfg.unsafe:
                    _log.debug(
                        'Renaming %s to %s', rules_file,
                        '{}.{}'.format(rules_file, timestamp)
                    )
                    os.rename(rules_file, '{}.{}'.format(rules_file, timestamp))
                    with open(rules_file, 'w') as f:
                        _log.debug('Writing new %s', rules_file)
                        f.write(new_config)
                else:
                    _log.debug('Would rename %s to %s', rules_file, '{}.{}'.format(rules_file, timestamp))
                    _log.info('Would have rewritten %s', rules_file)
            else:
                _log.debug('Rules are the same: keeping')
    return 0


if __name__ == '__main__':
    sys.exit(main())

