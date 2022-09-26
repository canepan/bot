import pytest

try:
    import ldap  # noqa

    skip_test_ldap = False
except ImportError:
    skip_test_ldap = True


@pytest.mark.skipif(skip_test_ldap, reason="ldap not available")
def test_printable():
    from tools.bin.ldap_browser import LdapBrowser
    from fixtures import ldap_browser_data

    print(LdapBrowser.printable(ldap_browser_data.input_data))
    print(ldap_browser_data.expected_output)
    assert LdapBrowser.printable(ldap_browser_data.input_data) == ldap_browser_data.expected_output
