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
# Fixtures (only patch *external* dependencies)
# --------------------------------------------------------------------------
@pytest.fixture
def mock_run(monkeypatch):
    """Patch subprocess.run (scp / ssh-keygen execution); default rc=0."""
    m = mock.Mock(return_value=mock.Mock(returncode=0))
    monkeypatch.setattr(scm.subprocess, "run", m)
    return m


@pytest.fixture
def which_ok(monkeypatch):
    """Pretend any external tool (scp, ssh-keygen) is found on PATH."""
    monkeypatch.setattr(scm.shutil, "which", lambda name: f"/usr/bin/{name}")


@pytest.fixture
def as_root(monkeypatch):
    monkeypatch.setattr(scm.getpass, "getuser", lambda: "root")


@pytest.fixture
def not_root(monkeypatch):
    monkeypatch.setattr(scm.getpass, "getuser", lambda: "bob")


@pytest.fixture
def keygen_output(monkeypatch):
    """Make `ssh-keygen -L` (subprocess.check_output) return given text."""

    def install(text=SAMPLE_L):
        monkeypatch.setattr(scm.subprocess, "check_output", lambda *a, **k: text)

    return install


@pytest.fixture
def menu_select(monkeypatch):
    """Drive questionary.select with a queue of answers."""

    def install(answers):
        it = iter(answers)
        sel = mock.Mock()
        sel.ask.side_effect = lambda: next(it)
        monkeypatch.setattr(scm.questionary, "select", lambda *a, **k: sel)

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


def test_parse_cert_invokes_ssh_keygen(keygen_output):
    keygen_output()
    info = scm.parse_cert("/x/host1_bob-cert.pub")
    assert info.key_id == "bob@example.com"


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
def test_list_certs(tmp_path, keygen_output):
    (tmp_path / "host1_bob-cert.pub").write_text("dummy")
    (tmp_path / "ignore.txt").write_text("nope")
    keygen_output()
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


def test_sign_missing_pubkey(tmp_path, mock_run):
    ca_key = tmp_path / "ca"
    ca_key.write_text("CA")
    ca = scm.SshCa(ssh_keygen="ssh-keygen", ca_key=str(ca_key), ssh_dir=str(tmp_path))
    assert ca.sign(host="host1", user="bob", identity="bob", principals="bob", validity="+52w") == 1
    mock_run.assert_not_called()


def test_sign_missing_ca_key(tmp_path, mock_run):
    ca = scm.SshCa(ssh_keygen="ssh-keygen", ca_key=str(tmp_path / "nope"), ssh_dir=str(tmp_path))
    assert ca.sign(host="host1", user="bob", identity="bob", principals="bob", validity="+52w") == 1
    mock_run.assert_not_called()


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


# --------------------------------------------------------------------------
# distribute
# --------------------------------------------------------------------------
def test_remote_cert_path():
    assert scm._remote_cert_path(".ssh/id_rsa.pub") == ".ssh/id_rsa-cert.pub"
    assert scm._remote_cert_path("/etc/ssh/custom") == "/etc/ssh/custom-cert.pub"


def test_distribute_cert_builds_scp_command(tmp_path, mock_run):
    (tmp_path / "host1_bob-cert.pub").write_text("CERT")
    rc = scm.distribute_cert(
        ssh_dir=str(tmp_path),
        host="host1",
        user="bob",
        remote_host="host1",
        ssh_user="bob",
        remote_key=".ssh/id_rsa.pub",
        scp="scp",
    )
    assert rc == 0
    assert mock_run.call_args.args[0] == [
        "scp",
        str(tmp_path / "host1_bob-cert.pub"),
        "bob@host1:.ssh/id_rsa-cert.pub",
    ]


def test_distribute_cert_missing(tmp_path, mock_run):
    rc = scm.distribute_cert(
        ssh_dir=str(tmp_path), host="h", user="u", remote_host="h", ssh_user="u", remote_key=".ssh/id_rsa.pub"
    )
    assert rc == 1
    mock_run.assert_not_called()


# --------------------------------------------------------------------------
# setup-host (configure sshd)
# --------------------------------------------------------------------------
def test_configure_sshd_requires_root(tmp_path, not_root):
    assert scm.configure_sshd(ca_pub=str(tmp_path / "ca.pub")) == 1


def test_configure_sshd_writes_files(tmp_path, as_root):
    ca_pub = tmp_path / "ca.pub"
    ca_pub.write_text("ssh-ed25519 AAAA ca")
    dest = tmp_path / "etc" / "ssh_user_ca.pub"
    conf = tmp_path / "etc" / "sshd_config.d" / "user_ca.conf"
    rc = scm.configure_sshd(ca_pub=str(ca_pub), trusted_ca_dest=str(dest), sshd_conf=str(conf))
    assert rc == 0
    assert dest.read_text() == "ssh-ed25519 AAAA ca"
    assert f"TrustedUserCAKeys {dest}" in conf.read_text()


def test_configure_sshd_idempotent(tmp_path, as_root):
    ca_pub = tmp_path / "ca.pub"
    ca_pub.write_text("ca")
    dest = tmp_path / "ssh_user_ca.pub"
    conf = tmp_path / "user_ca.conf"
    scm.configure_sshd(ca_pub=str(ca_pub), trusted_ca_dest=str(dest), sshd_conf=str(conf))
    scm.configure_sshd(ca_pub=str(ca_pub), trusted_ca_dest=str(dest), sshd_conf=str(conf))
    assert conf.read_text().count(f"TrustedUserCAKeys {dest}") == 1


def test_configure_sshd_missing_ca_pub(tmp_path, as_root):
    assert scm.configure_sshd(ca_pub=str(tmp_path / "nope.pub")) == 1


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def test_cli_list_empty(tmp_path):
    result = runner.invoke(scm.app, ["--ssh-dir", str(tmp_path), "list"])
    assert result.exit_code == 0
    assert "No certificates" in result.output


def test_cli_check_exit_code_critical(tmp_path, keygen_output):
    (tmp_path / "host1_bob-cert.pub").write_text("dummy")
    near = SAMPLE_L.replace(
        "to 2027-06-28T10:00:00",
        "to " + (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S"),
    )
    keygen_output(near)
    result = runner.invoke(scm.app, ["--ssh-dir", str(tmp_path), "check"])
    assert result.exit_code == 2


def test_cli_fetch_defaults_key_type_rsa(tmp_path, which_ok, mock_run):
    result = runner.invoke(scm.app, ["--ssh-dir", str(tmp_path), "fetch", "host1", "--user", "bob"])
    assert result.exit_code == 0
    cmd = mock_run.call_args.args[0]
    assert cmd[0].endswith("scp")
    assert cmd[1] == "bob@host1:.ssh/id_rsa.pub"
    assert cmd[2] == str(tmp_path / "host1_bob.pub")


def test_cli_fetch_key_type_override(tmp_path, which_ok, mock_run):
    result = runner.invoke(scm.app, ["--ssh-dir", str(tmp_path), "fetch", "host1", "-u", "bob", "-t", "ed25519"])
    assert result.exit_code == 0
    assert mock_run.call_args.args[0][1] == "bob@host1:.ssh/id_ed25519.pub"


def test_cli_fetch_remote_key_overrides_template(tmp_path, which_ok, mock_run):
    result = runner.invoke(
        scm.app, ["--ssh-dir", str(tmp_path), "fetch", "host1", "--remote-key", "/etc/ssh/custom.pub"]
    )
    assert result.exit_code == 0
    assert mock_run.call_args.args[0][1].endswith(":/etc/ssh/custom.pub")


def test_cli_distribute_defaults(tmp_path, which_ok, mock_run):
    (tmp_path / "host1_bob-cert.pub").write_text("CERT")
    result = runner.invoke(scm.app, ["--ssh-dir", str(tmp_path), "distribute", "host1", "-u", "bob"])
    assert result.exit_code == 0
    cmd = mock_run.call_args.args[0]
    assert cmd[1] == str(tmp_path / "host1_bob-cert.pub")
    assert cmd[2] == "bob@host1:.ssh/id_rsa-cert.pub"


def test_cli_setup_host_not_root(tmp_path, not_root):
    result = runner.invoke(scm.app, ["--ca-key", str(tmp_path / "ca"), "setup-host"])
    assert result.exit_code == 1


# --------------------------------------------------------------------------
# Interactive menu
# --------------------------------------------------------------------------
def test_cli_no_args_requires_tty():
    # CliRunner has no real TTY, so the menu path should refuse and exit 1.
    result = runner.invoke(scm.app, [])
    assert result.exit_code == 1
    assert "terminal" in result.output.lower() or "tty" in result.output.lower()


def test_menu_loop_quits_immediately(tmp_path, menu_select):
    ca = scm.SshCa(ssh_keygen="ssh-keygen", ca_key="/no/ca", ssh_dir=str(tmp_path))
    menu_select(["Quit"])
    scm.menu_loop(ca)  # returns without error (empty dir -> no certs)


def test_menu_loop_runs_action(tmp_path, menu_select, capsys):
    ca = scm.SshCa(ssh_keygen="ssh-keygen", ca_key="/no/ca", ssh_dir=str(tmp_path))
    menu_select(["List certificates", "Quit"])
    scm.menu_loop(ca)
    assert "No certificates" in capsys.readouterr().out
