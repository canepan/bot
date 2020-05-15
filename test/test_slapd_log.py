import os
import pytest

from tools.bin.slapd_log import LdapLog


@pytest.mark.parametrize('show_json,out_ext', ((False, 'out'), (True, 'json')))
def test_ldap_log(show_json, out_ext):
    ll = LdapLog(show_json=show_json)
    with open(os.path.join(os.path.dirname(__file__), 'fixtures', 'slapd-202005120558.log'), 'r') as fin:
        for line in fin:
            ll.parse_line(line)
    with open(os.path.join(os.path.dirname(__file__), 'fixtures', f'slapd-202005120558.{out_ext}'), 'r') as fout:
        assert fout.read().strip() == str(ll).strip()
