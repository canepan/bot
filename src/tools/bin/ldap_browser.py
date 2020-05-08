#!/mnt/opt/nicola/tools/bin/python
import attr
import argparse
import json
import ldap
import logging
import os
import sys
from getpass import getpass

if os.path.abspath(os.path.dirname(os.path.dirname(__file__))) not in sys.path:
    sys.path.insert(1, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
from tools.lib.parse_args import LoggingArgumentParser


APP_NAME = 'LDAPAdm'
_log = logging.getLogger('tools')


def parse_args(argv: list, descr='Manage/browse LDAP tree') -> argparse.Namespace:
    parser = LoggingArgumentParser(description=descr, app_name=APP_NAME)
    parser.add_argument(
        '--ldap-rc', '-L', default=os.path.join(os.environ['HOME'], '.ldaprc'), help='File to read instead of .ldaprc'
    )
    parser.add_argument(
        '--ldap-secret', '-S', default=os.path.join(os.environ['HOME'], '.ldap.secret'), help='Password file'
    )
    parser.add_argument('--ldap-bind-dn', '-D', default='cn=admin,dc=nicolacanepa,dc=net', help='LDAP base DN')
    parser.add_argument('--ldap-base', '-b', default='dc=nicolacanepa,dc=net', help='LDAP base DN')
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
            if line.startswith(f'{directive} '):
                return line.replace(directive, '').strip()


@attr.s
class Ldap(object):
    rc = attr.ib()
    pass_file = attr.ib()
    _secret = attr.ib(default=None)
    _base_dn = attr.ib(default=None)
    _bind_dn = attr.ib(default=None)
    _uri = attr.ib(default=None)

    def __attrs_post_init__(self):
        self._config = LdapRc(self.rc)
        self.__ldap = None

        if self._base_dn is None:
            self._base_dn = self._config.get('BASE')
        if self._bind_dn is None:
            self._bind_dn = self._config.get('BINDDN')
        if self._uri is None:
            self._uri = self._config.get('URI')
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
        return self._ldap.search_st(*args, base=self._base_dn, filterstr=filterstr, scope=ldap.SCOPE_SUBTREE, timeout=3, **kwargs)


def main(argv=sys.argv[1:]):
    cfg = parse_args(argv)
    l = Ldap(rc=cfg.ldap_rc, pass_file=cfg.ldap_secret)
    cfg.log.info(json.dumps(l.search(filterstr='uid=nicola'), indent=2, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
