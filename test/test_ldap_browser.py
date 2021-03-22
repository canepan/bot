from tools.bin.ldap_browser import LdapBrowser
from fixtures import ldap_browser_data


def test_printable():
    print(LdapBrowser.printable(ldap_browser_data.input_data))
    print(ldap_browser_data.expected_output)
    assert LdapBrowser.printable(ldap_browser_data.input_data) == ldap_browser_data.expected_output
