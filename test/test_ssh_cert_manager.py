from datetime import datetime, timedelta
from unittest import mock

import pytest
from typer.testing import CliRunner

from tools.bin import ssh_cert_manager as scm

runner = CliRunner()

# Sample `ssh-keygen -L -f <cert>` output (user certificate).
SAMPLE_L = """\
/home/bob/Documents/ssh/host1_bob-cert.pub:
        Type: ssh-rsa-cert-v01@openssh.com user certificate
        Public key: RSA-CERT SHA256:abcdef
        Signing CA: RSA SHA256:123456 (using rsa-sha2-512)
        Key ID: "bob@example.com"
        Serial: 0
        Valid: from 2026-06-29T10:00:00 to 2027-06-28T10:00:00
        Principals:
                bob
                admin
        Critical Options: (none)
        Extensions:
                permit-pty
"""


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
@pytest.fixture
def mock_run(monkeypatch):
    """Patch subprocess.run; default returns rc=0. Tests can tweak it."""
    m = mock.Mock(return_value=mock.Mock(returncode=0))
    monkeypatch.setattr(scm.subprocess, "run", m)
    return m


@pytest.fixture
def find_scp(monkeypatch):
    """Pretend scp is available on PATH."""
    monkeypatch.setattr(scm, "_find_scp", lambda: "scp")


@pytest.fixture
def captured_fetch(monkeypatch):
    """Capture the kwargs passed to fetch_public_key (returns the dict)."""
    captured = {}
    monkeypatch.setattr(scm, "fetch_public_key", lambda **kw: captured.update(kw) or 0)
    return captured


@pytest.fixture
def patch_parse(monkeypatch):
    """Install a fake parse_cert that parses the given -L text (default SAMPLE_L)."""

    def install(text=SAMPLE_L):
        monkeypatch.setattr(scm, "parse_cert", lambda path, kg=None: scm._parse_cert_text(path, text))

    return install


def _cert(days_to_expiry=None, forever=False):
    valid_to = None if (forever or days_to_expiry is None) else datetime.now() + timedelta(days=days_to_expiry)
    return scm.CertInfo(path="/x/c-cert.pub", key_id="id", valid_to=valid_to, forever=forever)


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------
def test_parse_cert_text():
    info = scm._parse_cert_text("/x/host1_bob-cert.pub", SAMPLE_L)
    assert info.key_id == "bob@example.com"
    assert info.serial == "0"
    assert info.principals == ["bob", "admin"]
    assert info.is_user_cert
    assert info.valid_from == datetime(2026, 6, 29, 10, 0, 0)
    assert info.valid_to == datetime(2027, 6, 28, 10, 0, 0)
    assert info.name == "host1_bob"
    assert not info.forever


def test_parse_cert_text_forever():
    text = SAMPLE_L.replace("Valid: from 2026-06-29T10:00:00 to 2027-06-28T10:00:00", "Valid: forever")
    info = scm._parse_cert_text("/x/c-cert.pub", text)
    assert info.forever
    assert info.valid_to is None


# --------------------------------------------------------------------------
# Expiry status
# --------------------------------------------------------------------------
def test_expiry_status_valid():
    _, status, style = scm._expiry_status(_cert(days_to_expiry=200))
    assert "valid" in status and style == "green"


def test_expiry_status_warning():
    _, status, style = scm._expiry_status(_cert(days_to_expiry=15))
    assert "expiring" in status and style == "yellow"


def test_expiry_status_critical():
    _, status, style = scm._expiry_status(_cert(days_to_expiry=3))
    assert "expiring" in status and style == "bold red"


def test_expiry_status_expired():
    _, status, style = scm._expiry_status(_cert(days_to_expiry=-5))
    assert "EXPIRED" in status and style == "bold red"


def test_expiry_status_forever():
    date_text, status, style = scm._expiry_status(_cert(forever=True))
    assert date_text == "never" and style == "green"


def test_xymon_report_worst_wins():
    certs = [_cert(days_to_expiry=200), _cert(days_to_expiry=2)]
    status, message = scm._xymon_report(certs, warn_days=30, crit_days=7)
    assert status == scm.XymonStatus.RED
    assert "&red" in message and "&green" in message


# --------------------------------------------------------------------------
# list_certs
# --------------------------------------------------------------------------
def test_list_certs(tmp_path, patch_parse):
    (tmp_path / "host1_bob-cert.pub").write_text("dummy")
    (tmp_path / "ignore.txt").write_text("nope")
    patch_parse()
    certs = scm.list_certs(str(tmp_path))
    assert [c.name for c in certs] == ["host1_bob"]


# --------------------------------------------------------------------------
# sign
# --------------------------------------------------------------------------
def test_sign_builds_expected_command(tmp_path, mock_run):
    ssh_dir = tmp_path / "ssh"
    ssh_dir.mkdir()
    ca_key = tmp_path / "ca"
    ca_key.write_text("CA")
    (ssh_dir / "host1_bob.pub").write_text("ssh-rsa AAAA bob")
    ca = scm.SshCa(ssh_keygen="ssh-keygen", ca_key=str(ca_key), ssh_dir=str(ssh_dir))

    rc = ca.sign(host="host1", user="bob", identity="bob@example.com", principals="bob", validity="+52w")
    assert rc == 0
    cmd = mock_run.call_args.args[0]
    assert cmd[0] == "ssh-keygen"
    assert "-s" in cmd and str(ca_key) in cmd
    assert cmd[cmd.index("-I") + 1] == "bob@example.com"
    assert cmd[cmd.index("-n") + 1] == "bob"
    assert cmd[cmd.index("-V") + 1] == "+52w"
    assert cmd[-1] == str(ssh_dir / "host1_bob.pub")


def test_sign_missing_pubkey(tmp_path):
    ca_key = tmp_path / "ca"
    ca_key.write_text("CA")
    ca = scm.SshCa(ssh_keygen="ssh-keygen", ca_key=str(ca_key), ssh_dir=str(tmp_path))
    assert ca.sign(host="host1", user="bob", identity="bob", principals="bob", validity="+52w") == 1


def test_sign_missing_ca_key(tmp_path):
    ca = scm.SshCa(ssh_keygen="ssh-keygen", ca_key=str(tmp_path / "nope"), ssh_dir=str(tmp_path))
    assert ca.sign(host="host1", user="bob", identity="bob", principals="bob", validity="+52w") == 1


# --------------------------------------------------------------------------
# fetch
# --------------------------------------------------------------------------
def test_fetch_public_key_builds_scp_command(tmp_path, mock_run):
    ssh_dir = tmp_path / "ssh"  # does not exist yet -> should be created
    rc = scm.fetch_public_key(
        ssh_dir=str(ssh_dir),
        host="host1",
        user="bob",
        remote_host="host1",
        ssh_user="bob",
        remote_key=".ssh/id_rsa.pub",
        scp="scp",
    )
    assert rc == 0
    assert ssh_dir.is_dir()  # created
    assert mock_run.call_args.args[0] == ["scp", "bob@host1:.ssh/id_rsa.pub", str(ssh_dir / "host1_bob.pub")]


def test_fetch_public_key_scp_missing(tmp_path, mock_run):
    mock_run.side_effect = FileNotFoundError()
    rc = scm.fetch_public_key(
        ssh_dir=str(tmp_path), host="h", user="u", remote_host="h", ssh_user="u", remote_key="k", scp="scp"
    )
    assert rc == 127


def test_cli_fetch_defaults_key_type_rsa(tmp_path, find_scp, captured_fetch):
    result = runner.invoke(scm.app, ["--ssh-dir", str(tmp_path), "fetch", "host1", "--user", "bob"])
    assert result.exit_code == 0
    # remote_host/ssh_user default to host/user; remote_key built from the rsa template.
    assert captured_fetch["remote_host"] == "host1"
    assert captured_fetch["ssh_user"] == "bob"
    assert captured_fetch["remote_key"] == ".ssh/id_rsa.pub"


def test_cli_fetch_key_type_override(tmp_path, find_scp, captured_fetch):
    result = runner.invoke(
        scm.app, ["--ssh-dir", str(tmp_path), "fetch", "host1", "-u", "bob", "--key-type", "ed25519"]
    )
    assert result.exit_code == 0
    assert captured_fetch["remote_key"] == ".ssh/id_ed25519.pub"


def test_cli_fetch_remote_key_overrides_template(tmp_path, find_scp, captured_fetch):
    result = runner.invoke(
        scm.app,
        ["--ssh-dir", str(tmp_path), "fetch", "host1", "--remote-key", "/etc/ssh/custom.pub", "--key-type", "rsa"],
    )
    assert result.exit_code == 0
    assert captured_fetch["remote_key"] == "/etc/ssh/custom.pub"


# --------------------------------------------------------------------------
# CLI: list / check
# --------------------------------------------------------------------------
def test_cli_list_empty(tmp_path):
    result = runner.invoke(scm.app, ["--ssh-dir", str(tmp_path), "list"])
    assert result.exit_code == 0
    assert "No certificates" in result.output


def test_cli_check_exit_code_critical(tmp_path, patch_parse):
    (tmp_path / "host1_bob-cert.pub").write_text("dummy")
    near = SAMPLE_L.replace(
        "to 2027-06-28T10:00:00",
        "to " + (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S"),
    )
    patch_parse(near)
    result = runner.invoke(scm.app, ["--ssh-dir", str(tmp_path), "check"])
    assert result.exit_code == 2


# --------------------------------------------------------------------------
# Interactive menu
# --------------------------------------------------------------------------
def test_cli_no_args_requires_tty():
    # CliRunner has no real TTY, so the menu path should refuse and exit 1.
    result = runner.invoke(scm.app, [])
    assert result.exit_code == 1
    assert "terminal" in result.output.lower() or "tty" in result.output.lower()


@pytest.fixture
def menu_select(monkeypatch):
    """Drive questionary.select with a queue of answers."""

    def install(answers):
        it = iter(answers)
        sel = mock.Mock()
        sel.ask.side_effect = lambda: next(it)
        monkeypatch.setattr(scm.questionary, "select", lambda *a, **k: sel)

    return install


def test_menu_loop_quits_immediately(menu_select):
    ca = scm.SshCa(ssh_keygen="ssh-keygen", ca_key="/no/ca", ssh_dir="/no/dir")
    menu_select(["Quit"])
    scm.menu_loop(ca)  # returns without error (missing dir -> no certs)


def test_menu_loop_runs_action(menu_select, monkeypatch):
    ca = scm.SshCa(ssh_keygen="ssh-keygen", ca_key="/no/ca", ssh_dir="/tmp")
    menu_select(["List certificates", "Quit"])
    lc = mock.Mock(return_value=[])
    monkeypatch.setattr(scm, "list_certs", lc)
    scm.menu_loop(ca)
    assert lc.called
