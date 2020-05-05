#!/mnt/opt/nicola/tools/bin/python
import attr
import configargparse
import ldap
import logging
import os
import sys

if os.path.abspath(os.path.dirname(os.path.dirname(__file__))) not in sys.path:
    sys.path.insert(1, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
from tools.lib import logging_utils


APP_NAME = 'LDAPAdm'
_log = logging.getLogger('tools')


def parse_args(argv: list, descr='Manage/browse LDAP tree') -> configargparse.Namespace:
    parser = configargparse.ArgumentParser(
        description=descr,
        formatter_class=configargparse.ArgumentDefaultsHelpFormatter,
        default_config_files=[],
    )
    parser.add_argument(
        '--ldap-rc', '-L', default=os.path.join(os.environ['HOME'], '.ldaprc'), help='File to read instead of .ldaprc'
    )
    parser.add_argument(
        '--ldap-secret', '-S', default=os.path.join(os.environ['HOME'], '.ldap.secret'), help='Password file'
    )
    parser.add_argument('--ldap-bind-dn', '-D', default='cn=admin,dc=nicolacanepa,dc=net', help='LDAP base DN')
    parser.add_argument('--ldap-base', '-b', default='dc=nicolacanepa,dc=net', help='LDAP base DN')
    parser.add_argument('--config', '-c', is_config_file=True, help='{} config file'.format(APP_NAME))
    g = parser.add_mutually_exclusive_group()
    g.add_argument('-q', '--quiet', action='store_true')
    g.add_argument('-v', '--verbose', action='store_true')
    cfg = parser.parse_args(argv)
    cfg.log = logging_utils.get_logger('tools', verbose=cfg.verbose, quiet=cfg.quiet)
    return cfg


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
            if line.startswith(directive):
                return line.replace(directive, '').strip()


@attr.s
class Ldap(object):
    # BASE dc=nicolacanepa,dc=net
    # URI ldaps://ldap1.nicolacanepa.net ldap://ldap1.nicolacanepa.net
    # BINDDN cn=admin,dc=nicolacanepa,dc=net
    rc = attr.ib()
    pass_file = attr.ib()
    _secret = attr.ib(default=None)
    _base_dn = attr.ib(default=None)
    _bind_dn = attr.ib(default=None)
    _uri = attr.ib(default=None)

    def __attrs_post_init__(self):
        self._config = LdapRc(self.rc)
        self.__ldap = None

        if self._secret is None:
            try:
                with open(self.pass_file, 'r') as f:
                    self._secret = f.read()
            except Exception as e:
                _log.error('Password file not found: %s', e)
        if self._base_dn is None:
            self._base_dn = self._config.get('BASE')
        if self._bind_dn is None:
            self._bind_dn = self._config.get('BINDDN')
        if self._uri is None:
            self._uri = self._config.get('URI')

    @property
    def _ldap(self):
        if self.__ldap is None:
            self.__ldap = ldap.initialize(self._uri)
            self._bind_result = self.__ldap.simple_bind_s(self._bind_dn, self._secret)
            _log.debug('Bind result: %s', self._bind_result)
        return self.__ldap

    def search(self, *args, **kwargs):
        return self._ldap.search(*args, **kwargs)


def main(argv=sys.argv[1:]):
    cfg = parse_args(argv)
    l = Ldap(rc=cfg.ldap_rc, pass_file=cfg.ldap_secret)
    cfg.log.info(l.search('uid=nicola'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
