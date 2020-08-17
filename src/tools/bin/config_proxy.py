#!/mnt/opt/nicola/tools/bin/python3
import attr
import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime
from functools import lru_cache

if os.path.abspath(os.path.dirname(os.path.dirname(__file__))) not in sys.path:
    sys.path.insert(1, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
from ..libs import text_utils
from ..libs.parse_args import LoggingArgumentParser


APP_NAME = 'canepa.proxy.config'
ETC_E2_DIR = '/etc/e2guardian'
ETC_SG_FILE = '/etc/squidguard/squidGuard.conf'

_log = logging.getLogger('tools')


def parse_args(argv: list, descr: str = 'Create e2g configuration') -> argparse.Namespace:
    parser = LoggingArgumentParser(description=descr, app_name=APP_NAME)
    parser.add_argument('--categories', nargs='+', default=['adult', 'games'], help='Categories to ban')
    parser.add_argument(
        '--filter-types', nargs='+', default=['banned', 'weighted'], help='Filter types: sitelist, urllist will be appended'
    )
    parser.add_argument(
        '--rules-dir', '-r', default='kids', help='Directory with the rules files (relative to {})'.format(ETC_E2_DIR)
    )
    parser.add_argument('--unsafe', action='store_true', help='Really write/rename files')
    parser.add_argument(
        '--format', choices=('e2guardian', 'squidguard'), default='e2guardian', help='Configure the specified package'
    )
    return parser.parse_args(argv)


def file_content(filename):
    with open(filename) as f:
        return f.read()


@attr.s
class Category(object):
    category_map = {'sitelist': 'domains', 'urllist': 'urls', 'phraselist': 'weighted'}
    list_map = {'sitelist': 'blacklists', 'urllist': 'blacklists', 'phraselist': 'phraselists'}
    category_name = attr.ib()

    def _list_file(self, category_type: str):
        return f'{ETC_E2_DIR}/lists/{self.list_map[category_type]}/{self.category_name}/{self.category_map[category_type]}'

    def exists(self, *category_types):
        if not category_types:
            category_types = self.list_map.keys()
        return any(os.path.isfile(self._list_file(category_type)) for category_type in category_types)


@attr.s
class E2Category(Category):
    '''
    An E2 config is made of:
    * e2configfX.conf (contains references to content filtering files, i.e. bannedXXX/weightedXXX)
    * each bannedXXX/weightedXXX file contains references to the blocked category files
    * the content filtering filename is made of blacklists/<category>/<list_type> or phraselists/<category>/<list_type>:
      - <category> can be adult, games, etc
      - list_type is either domains, urls or weighted
    '''
    FILE_HEADER = {
        'sitelist': '.Include</etc/e2guardian/kids/bannedtimes>\n',
        'urllist': '.Include</etc/e2guardian/kids/bannedtimes>\n',
        'phraselist': '.Include</etc/e2guardian/kids/bannedtimes>\n',
    }
    FILE_FOOTER = {'sitelist': '', 'urllist': '', 'phraselist': ''}

    def line(self, category_type: str):
        '''Return the line in a content filtering file to block my category for tye specified type'''
        return f'.Include<{self._list_file(category_type)}>'

    @classmethod
    def filter_file(cls, basename, category_type, rules_dir):
        return os.path.join(ETC_E2_DIR, rules_dir, '{}{}'.format(basename, category_type))

    @classmethod
    @lru_cache(maxsize=10)
    def filter_exists(cls, basename: str, category_type: str, rules_dir: str) -> bool:
        fname = cls.filter_file(basename, category_type, rules_dir)
        _log.debug('Checking config %s', fname)
        return os.path.isfile(fname)


@attr.s
class SGCategory(Category):
    '''
    A SquidGuard config is made of:
    * squidguard.conf (contains stanzas for content filtering categories, i.e. games, adult, etc (custom names)
    * each stanza contains references to the blocked content filtering files
    * the content filtering filename is made of blacklists/<category>/<list_type>:
      - <category> can be adult, games, etc
      - list_type is either domains, urls or expressions
    '''
    FILE_HEADER = '''
# Caution: do NOT use comments inside { }

dbhome /var/lib/squidguard/db
logdir /var/log/squidguard

time workhours {
        weekly mtwhf 07:00 - 18:30
}
src kids {
    iplist /etc/squidguard/kids.list
}
dest good {
        urllist    /etc/e2guardian/kids/exceptionurllist
        domainlist /etc/e2guardian/kids/exceptionsitelist
}
dest local {
}
'''
    FILE_FOOTER = '''
acl {
        kids within workhours {
                pass     good<blocked_list> any
#        } else {
#                pass any
        }

        default {
                pass     local none
                redirect http://Sito_Vietato_O_Fuori_Orario_clientaddr=%a_clientname=%n_clientuser=%i_clientgroup=%s_targetgroup=%t_url=%u
        }
}
'''
    category_map = {'domainlist': 'domains', 'urllist': 'urls', 'expressionlist': 'expressions'}
    list_map = {'domainlist': 'blacklists', 'urllist': 'blacklists', 'expressionlist': 'blacklists'}
    filter_types: list = attr.ib()

    def stanza(self):
        stanza = f'dest {self.category_name} {{\n'
        for list_type, mapped_type in self.category_map.items():
            if self.exists(list_type):
                stanza += f'       {list_type:14} {self.category_name}/{mapped_type}\n'
        stanza += '}'
        return stanza


def replace_if_changed(rules_file: str, new_config: str, unsafe: bool) -> int:
    current_config = file_content(rules_file)
    if new_config.strip().replace('\t', ' ') != current_config.strip().replace('\t', ' '):
        _log.info('"%s" differs: replacing', rules_file)
        _log.debug('Full difference:\n%s', text_utils.CompareContents(
            current_config, new_config,
            old_file_name=f'current {rules_file}', new_file_name=f'proposed {rules_file}'
        ))
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        if unsafe:
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
        return 1
    else:
        _log.info('Rules in %s are the same: keeping', rules_file)
        return 0


def configure_squidguard(cfg):
    categories = [SGCategory(c, cfg.filter_types) for c in cfg.categories]
    changed_files = 0
    valid_categories = [category for category in categories if category.exists()]
    new_config = '{}\n\n{}\n\n{}'.format(
        SGCategory.FILE_HEADER,
        '\n'.join([category.stanza() for category in valid_categories]),
        SGCategory.FILE_FOOTER.replace(
            '<blocked_list>', " !".join(([''] if valid_categories else []) + [category.category_name for category in valid_categories])
        ),
    )
    config_file = ETC_SG_FILE
    changed_files = replace_if_changed(config_file, new_config, cfg.unsafe)
    return changed_files


def configure_e2guardian(cfg):
    categories = [E2Category(c) for c in cfg.categories]
    changed_files = 0
    for ft in cfg.filter_types:
        for ctype in (c for c in ('sitelist', 'urllist', 'phraselist') if E2Category.filter_exists(ft, c, cfg.rules_dir)):
            new_config = '{}{}{}'.format(
                E2Category.FILE_HEADER[ctype],
                '\n'.join([category.line(ctype) for category in categories if category.exists(ctype)]),
                E2Category.FILE_FOOTER[ctype],
            )
            rules_file = E2Category.filter_file(ft, ctype, cfg.rules_dir)
            changed_files += replace_if_changed(rules_file, new_config, cfg.unsafe)
    return changed_files


def main(argv=sys.argv[1:]):
    cfg = parse_args(argv)
    cfg.log.info('About to ban %s', cfg.categories)
    if cfg.format == 'e2guardian':
        changed_files = configure_e2guardian(cfg)
    elif cfg.format == 'squidguard':
        changed_files = configure_squidguard(cfg)
    if changed_files == 0:
        _log.error('No files to change')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
