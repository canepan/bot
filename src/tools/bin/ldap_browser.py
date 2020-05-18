#!/mnt/opt/nicola/tools/bin/python
import attr
import argparse
import json
import ldap
import logging
import os
import re
import sys
from getpass import getpass

if os.path.abspath(os.path.dirname(os.path.dirname(__file__))) not in sys.path:
    sys.path.insert(1, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
from tools.lib.parse_args import LoggingArgumentParser


APP_NAME = 'LDAPAdm'
_log = logging.getLogger(APP_NAME)


def parse_args(argv: list, descr='Manage/browse LDAP tree') -> argparse.Namespace:
    parser = LoggingArgumentParser(description=descr, app_name=APP_NAME)
    parser.add_argument('filterstr', default='*', help='Filter reults')
    parser.add_argument(
        '--ldap-rc', '-L', default=os.path.join(os.environ['HOME'], '.ldaprc'), help='File to read instead of .ldaprc'
    )
    parser.add_argument(
        '--ldap-secret', '-y', default=os.path.join(os.environ['HOME'], '.ldap.secret'), help='Password file'
    )
    parser.add_argument('--ldap-bind-dn', '-D', default=None, help='LDAP base DN')
    parser.add_argument('--ldap-base', '-b', default=None, help='LDAP base DN')
    parser.add_argument('--ldap-attrs', '-a', default=None, nargs='+', help='LDAP attrs')
    parser.add_argument('--json', '-j', action='store_true', help='Output in JSON format')
    return parser.parse_args(argv)


class LdapRc(object):
    def __init__(self, config_file):
        self._config_file = config_file
        self._config = None

    @property
    def config(self):
        if self._config is None:
            with open(self._config_file, 'r') as f:
                self._config = f.readlines()
        return self._config

    def get(self, directive: str) -> str:
        for line in self.config:
            if re.match(f'{directive}\s', line):
                return line.replace(directive, '').strip()


@attr.s
class LdapBrowser(object):
    rc = attr.ib()
    pass_file = attr.ib()
    _secret = attr.ib(default=None)
    _base_dn = attr.ib(default=None)
    _bind_dn = attr.ib(default=None)
    _config_suffix = attr.ib(default='')
    _uri = attr.ib(default=None)
    verbose = attr.ib(default=False)

    def __attrs_post_init__(self):
        self._config = LdapRc(self.rc)
        self.__ldap = None

        if self._base_dn is None:
            self._base_dn = self._config.get(f'BASE{self._config_suffix}')
            _log.debug('base_dn: %s', self._base_dn)
        if self._bind_dn is None:
            self._bind_dn = self._config.get(f'BINDDN{self._config_suffix}')
            _log.debug('bind_dn: %s', self._bind_dn)
        if self._uri is None:
            self._uri = self._config.get('URI') or 'ldap://127.0.0.1:389'
            _log.debug('uri: %s', self._uri)
        if self._secret is None:
            try:
                with open(self.pass_file, 'r') as f:
                    self._secret = f.read()
            except Exception as e:
                _log.debug('Password file not found: %s', e)
                self._secret = getpass(f'Please insert LDAP password for {self._bind_dn}: ')

    @property
    def _ldap(self):
        if self.__ldap is None:
            self.__ldap = ldap.initialize(self._uri)
            self._bind_result = self.__ldap.simple_bind_s(self._bind_dn, self._secret)
            _log.debug('Bind result: %s', self._bind_result)
        return self.__ldap

    def search(self, filterstr, *args, **kwargs):
        _log.debug('Query: ldapsearch -b %s -D %s -y %s %s %s',
                   self._base_dn, self._bind_dn, self.pass_file,
                   filterstr, ' '.join(kwargs.get('attrlist') or []))
        ldap_result = self._ldap.search_st(
            *args, base=self._base_dn, filterstr=filterstr, scope=ldap.SCOPE_SUBTREE, timeout=3, **kwargs
        )
        return compact_dict(ldap_result)

    @classmethod
    def printable(cls, ldap_data, as_json: bool = False, indent: int = 0) -> str:
        if as_json:
            return json.dumps(ldap_data, indent=2, default=str)
        verbose = _log.isEnabledFor(logging.DEBUG)
        lines = []
        processing_done = False
        try:
            result_dict = {}
            for k, v in ldap_data.items():
                pv = cls.printable(v, indent=indent + 1)
                if pv and (verbose or k != 'krbExtraData'):
                    lines.append(f'{indent * "  "}{k}: {pv.lstrip(" ")}')
            processing_done = True
        except AttributeError:
            pass
        if processing_done is False:
            try:
                lines.append(ldap_data.decode('utf-8'))
                processing_done = True
            except (AttributeError, UnicodeDecodeError):
                pass
        if processing_done is False:
            try:
                if ldap_data.isascii():
                    lines.append(f'{indent * "  "}{ldap_data}')
                elif verbose:
                    lines.append(f'{indent * "  "}{repr(ldap_data)}')
                processing_done = True
            except AttributeError:
                pass
        if processing_done is False:
            try:
                result_list = []
                for k in ldap_data:
                    pk = cls.printable(k, indent=indent)
                    if pk.strip():
                        result_list.append(pk)
                processing_done = True
                lines.append('\n'.join(result_list))
                processing_done = True
            except AttributeError:
                pass
        return '\n'.join(lines)

def compact_dict(orig_dict):
    # dict
    try:
        result_dict = {}
        for k, v in orig_dict.items():
            if v:
                result_dict[k] = compact_dict(v)
        return result_dict
    except AttributeError:
        pass
    # decodable str
    try:
        return orig_dict.decode('utf-8')
    except (AttributeError, UnicodeDecodeError):
        pass
    # str
    try:
        return orig_dict.strip()
    except AttributeError:
        pass
    # iterable
    try:
        result_list = []
        for k in orig_dict:
            if k:
                result_list.append(compact_dict(k))
        if len(result_list) == 1:
            return result_list[0]
        return result_list
    except AttributeError:
        pass
    return orig_dict


def main(argv=sys.argv[1:]):
    cfg = parse_args(argv)
    args = {
        'rc': cfg.ldap_rc,
        'pass_file': cfg.ldap_secret,
        'base_dn': cfg.ldap_base,
        'bind_dn': cfg.ldap_bind_dn,
        'verbose': cfg.verbose,
    }
    if cfg.filterstr == 'AccessLists':
        args['config_suffix'] =  'CONFIG'
        search_args = {'filterstr': 'olcAccess=*', 'attrlist': ['olcAccess']}
    else:
        search_args = {'filterstr': cfg.filterstr, 'attrlist': cfg.ldap_attrs}
    l = LdapBrowser(**args)
    cfg.log.info(l.printable(l.search(**search_args), as_json=cfg.json))
    return 0


if __name__ == '__main__':
    sys.exit(main())
