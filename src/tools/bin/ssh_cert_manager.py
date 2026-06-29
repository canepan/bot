#!/usr/bin/env python3
"""ssh-cert-manager - manage SSH **user** (client) certificates signed by an SSH CA.

This is the Python counterpart of ``shell/bin/ssh_ca_sign.sh``. It signs a user's
public key with a user-CA private key (``ssh-keygen -s``), lists the issued
certificates, and checks their expiry (optionally reporting to Xymon).

Workflow (see https://dev.to/gvelrajan/how-to-configure-and-setup-ssh-certificates-for-ssh-authentication-b52):
  * a user CA key pair lives at ``~/.ssh/ssh_user_ca`` (private) / ``.pub`` (public)
  * the CA public key is trusted on hosts via ``TrustedUserCAKeys`` in sshd_config
  * a user public key (``<host>_<user>.pub``) is signed into ``<host>_<user>-cert.pub``

Sub-commands (or run with no sub-command for an interactive menu):
  * ``fetch``  copy a user's public key from a remote host into the ssh-dir
  * ``sign``   create/update (re-sign) a user certificate
  * ``list``   show issued certificates with principals and expiry
  * ``check``  report expiry status (exit 0/1/2 = ok/warning/critical), optionally to Xymon

Dependencies: typer, questionary, rich (and the system ``ssh-keygen``/``scp``).
"""

import getpass
import logging
import re
import shutil
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional, Tuple

import attr
import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

try:  # shared helper that talks to the Xymon server
    from ..libs.xymon import Xymon, XymonStatus
except (ImportError, ValueError):  # running as a plain script
    try:
        from tools.libs.xymon import Xymon, XymonStatus
    except ImportError:  # Xymon support unavailable
        Xymon = None  # type: ignore
        XymonStatus = None  # type: ignore

APP_NAME = "ssh-cert-manager"
console = Console()

# Defaults mirror shell/bin/ssh_ca_sign.sh.
DEFAULT_SSH_DIR = str(Path.home() / "Documents" / "ssh")
DEFAULT_CA_KEY = str(Path.home() / ".ssh" / "ssh_user_ca")
DEFAULT_VALIDITY = "+52w"
CERT_SUFFIX = "-cert.pub"
# Public-key path on the remote host (relative to the login home). {key_type}
# is filled from --key-type (default below); --remote-key overrides it entirely.
REMOTE_KEY_TEMPLATE = ".ssh/id_{key_type}.pub"
DEFAULT_KEY_TYPE = "rsa"

# Expiry thresholds (days) used by `check`/Xymon.
WARN_DAYS = 30
CRIT_DAYS = 7
XYMON_CHECK_NAME = "sshcerts"


@attr.define
class CertInfo:
    """Parsed details of a signed SSH certificate (from ``ssh-keygen -L``)."""

    path: str
    key_id: str = ""
    cert_type: str = ""
    serial: str = ""
    principals: List[str] = attr.field(factory=list)
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    forever: bool = False

    @property
    def name(self) -> str:
        base = Path(self.path).name
        return base[: -len(CERT_SUFFIX)] if base.endswith(CERT_SUFFIX) else base

    @property
    def is_user_cert(self) -> bool:
        return "user" in self.cert_type.lower()


def _find_ssh_keygen() -> Optional[str]:
    return shutil.which("ssh-keygen")


def _find_scp() -> Optional[str]:
    return shutil.which("scp")


def fetch_public_key(
    ssh_dir: str,
    host: str,
    user: str,
    remote_host: str,
    ssh_user: str,
    remote_key: str,
    scp: str = "scp",
) -> int:
    """Copy a remote public key into ``ssh_dir`` as ``<host>_<user>.pub`` via scp.

    The destination filename is what :meth:`SshCa.sign` expects. Returns the
    scp exit code (127 if scp is missing).
    """
    ssh_path = Path(ssh_dir)
    ssh_path.mkdir(parents=True, exist_ok=True)
    dest = ssh_path / f"{host}_{user}.pub"
    src = f"{ssh_user}@{remote_host}:{remote_key}"
    cmd = [scp, src, str(dest)]
    console.print("$ " + " ".join(cmd), style="dim")
    try:
        result = subprocess.run(cmd)
    except FileNotFoundError:
        console.print(f"scp not found: {scp}", style="bold red")
        return 127
    if result.returncode == 0:
        console.print(f"Fetched public key -> {dest}", style="green")
    else:
        console.print(f"scp failed (exit {result.returncode}).", style="bold red")
    return result.returncode


def _default_domain() -> str:
    """Best-effort local domain (the part of the FQDN after the first dot)."""
    fqdn = socket.getfqdn()
    return fqdn.split(".", 1)[1] if "." in fqdn else ""


def _parse_dt(text: str) -> Optional[datetime]:
    """Parse an ssh-keygen validity timestamp (local time, naive)."""
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def parse_cert(path: str, ssh_keygen: Optional[str] = None) -> CertInfo:
    """Parse a certificate file via ``ssh-keygen -L -f <path>``.

    Raises ``OSError``/``subprocess.CalledProcessError`` if the file cannot be read.
    """
    keygen = ssh_keygen or _find_ssh_keygen() or "ssh-keygen"
    out = subprocess.check_output([keygen, "-L", "-f", path], universal_newlines=True, stderr=subprocess.DEVNULL)
    return _parse_cert_text(path, out)


def _parse_cert_text(path: str, text: str) -> CertInfo:
    """Parse the textual output of ``ssh-keygen -L`` into a :class:`CertInfo`."""
    info = CertInfo(path=path)
    in_principals = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Principals:"):
            in_principals = True
            continue
        if in_principals:
            # The principals block is an indented list; any other "Key:" ends it.
            if line.startswith((" ", "\t")) and ":" not in stripped and stripped:
                info.principals.append(stripped)
                continue
            in_principals = False
        if stripped.startswith("Type:"):
            info.cert_type = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Key ID:"):
            info.key_id = stripped.split(":", 1)[1].strip().strip('"')
        elif stripped.startswith("Serial:"):
            info.serial = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Valid:"):
            value = stripped.removeprefix("Valid:").strip()
            if "forever" in value or value == "always":
                info.forever = True
            else:
                m = re.search(r"from (\S+) to (\S+)", value)
                if m:
                    info.valid_from = _parse_dt(m.group(1))
                    info.valid_to = _parse_dt(m.group(2))
    return info


def list_certs(ssh_dir: str, ssh_keygen: Optional[str] = None) -> List[CertInfo]:
    """Parse every ``*-cert.pub`` in ``ssh_dir`` (unparseable files are skipped)."""
    ssh_path = Path(ssh_dir)
    if not ssh_path.is_dir():
        return []
    certs = []
    for entry in sorted(ssh_path.iterdir()):
        if not entry.name.endswith(CERT_SUFFIX):
            continue
        try:
            certs.append(parse_cert(str(entry), ssh_keygen))
        except (OSError, subprocess.CalledProcessError):
            continue
    return certs


def _days_left(cert: CertInfo, now: Optional[datetime] = None) -> Optional[int]:
    if cert.forever:
        return None
    if cert.valid_to is None:
        return None
    return (cert.valid_to - (now or datetime.now())).days


def _expiry_status(cert: CertInfo, now: Optional[datetime] = None) -> Tuple[str, str, str]:
    """Map a cert's expiry to (date_text, status_text, rich_style)."""
    if cert.forever:
        return ("never", "valid (forever)", "green")
    if cert.valid_to is None:
        return ("unknown", "unknown", "dim")
    days = _days_left(cert, now)
    date_text = cert.valid_to.strftime("%Y-%m-%d")
    if days is None:
        return (date_text, "unknown", "dim")
    if days < 0:
        return (date_text, f"EXPIRED ({-days}d ago)", "bold red")
    if days <= CRIT_DAYS:
        return (date_text, f"expiring ({days}d)", "bold red")
    if days <= WARN_DAYS:
        return (date_text, f"expiring ({days}d)", "yellow")
    return (date_text, f"valid ({days}d)", "green")


def _render_table(certs: List[CertInfo]) -> Table:
    table = Table(title="SSH certificates", show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Certificate")
    table.add_column("Key ID")
    table.add_column("Principals")
    table.add_column("Expires")
    table.add_column("Status")
    for idx, cert in enumerate(certs, 1):
        date_text, status_text, style = _expiry_status(cert)
        table.add_row(
            str(idx),
            cert.name,
            cert.key_id or "[dim]-[/dim]",
            ", ".join(cert.principals) or "[dim]-[/dim]",
            date_text,
            f"[{style}]{status_text}[/{style}]",
        )
    return table


def _xymon_report(certs: List[CertInfo], warn_days: int, crit_days: int):
    """Build (XymonStatus, message) describing certificate expiry (worst wins)."""
    severity = {"green": 0, "yellow": 1, "red": 2}
    overall = "green"
    if not certs:
        return XymonStatus.YELLOW, "&yellow No SSH certificates found."
    now = datetime.now()
    lines = []
    graphs = []
    for cert in certs:
        if cert.forever:
            color, detail, days = "green", "valid (forever)", None
        elif cert.valid_to is None:
            color, detail, days = "yellow", "expiry unknown", None
        else:
            days = (cert.valid_to - now).days
            date_text = cert.valid_to.strftime("%Y-%m-%d")
            if days < 0:
                color, detail = "red", f"EXPIRED {date_text} ({-days} days ago)"
            elif days <= crit_days:
                color, detail = "red", f"expires {date_text} ({days} days)"
            elif days <= warn_days:
                color, detail = "yellow", f"expires {date_text} ({days} days)"
            else:
                color, detail = "green", f"expires {date_text} ({days} days)"
        if severity[color] > severity[overall]:
            overall = color
        lines.append(f"&{color} {cert.name}: {detail}")
        if days is not None:
            graphs.append(f"{cert.name.replace('.', '_')}.days : {days}")
    status = {"green": XymonStatus.GREEN, "yellow": XymonStatus.YELLOW, "red": XymonStatus.RED}[overall]
    header = f"SSH certificate expiry ({len(certs)} certs, warn<{warn_days}d, crit<{crit_days}d)"
    body = "\n".join(lines)
    graphs_text = "\n".join(graphs)
    return status, f"{header}\n{body}\n\n{graphs_text}"


def _publish_xymon(certs: List[CertInfo], check_name: str, warn_days: int, crit_days: int, dry_run: bool) -> int:
    if Xymon is None or XymonStatus is None:
        console.print("Xymon support is unavailable (could not import tools.libs.xymon).", style="bold red")
        return 2
    status, message = _xymon_report(certs, warn_days=warn_days, crit_days=crit_days)
    if dry_run:
        logging.basicConfig(level=logging.DEBUG)
        console.print(f"[dim]Xymon status:[/dim] {status.value}\n{message}")
    try:
        Xymon(SimpleNamespace(debug=dry_run), APP_NAME, check_name).send_status(status, message, "24h")
    except Exception as exc:  # network/binary errors shouldn't crash the CLI
        console.print(f"Failed to send to Xymon: {exc}", style="bold red")
        return 1
    console.print(f"Published '{check_name}' status to Xymon: {status.value}", style="green")
    return 0


@attr.define
class SshCa:
    """Thin wrapper around ``ssh-keygen`` for signing user certificates."""

    ssh_keygen: str
    ca_key: str
    ssh_dir: str

    def sign(self, host: str, user: str, identity: str, principals: str, validity: str) -> int:
        """Sign ``<ssh_dir>/<host>_<user>.pub`` -> ``<host>_<user>-cert.pub``."""
        ca_key = Path(self.ca_key)
        if not ca_key.is_file():
            console.print(f"CA private key not found: {ca_key}", style="bold red")
            return 1
        pubkey = Path(self.ssh_dir) / f"{host}_{user}.pub"
        if not pubkey.is_file():
            console.print(f"Public key not found: {pubkey}", style="bold red")
            return 1
        cmd = [self.ssh_keygen, "-s", str(ca_key), "-I", identity, "-n", principals, "-V", validity, str(pubkey)]
        console.print("$ " + " ".join(cmd), style="dim")
        try:
            result = subprocess.run(cmd)
        except FileNotFoundError:
            console.print(f"ssh-keygen not found: {self.ssh_keygen}", style="bold red")
            return 127
        if result.returncode == 0:
            cert = pubkey.with_name(f"{pubkey.stem}{CERT_SUFFIX}")
            console.print(f"Signed cert for {identity} (principals: {principals}) -> {cert}", style="green")
        else:
            console.print(f"ssh-keygen failed (exit {result.returncode}).", style="bold red")
        return result.returncode


# ---------------------------------------------------------------------------
# Interactive menu (questionary)
# ---------------------------------------------------------------------------
def _ask_text(message: str, default: str = "") -> Optional[str]:
    """Prompt for text; returns None if cancelled (Ctrl-C)."""
    return questionary.text(message, default=default).ask()


def _ask_confirm(message: str, default: bool = False) -> bool:
    return bool(questionary.confirm(message, default=default).ask())


def action_fetch(ca: "SshCa") -> None:
    scp = _find_scp()
    if not scp:
        console.print("Could not find the 'scp' executable.", style="bold red")
        return
    host = _ask_text("Host label (for the local filename <host>_<user>.pub)")
    if not host:
        return
    user = _ask_text("User id / login", default=getpass.getuser()) or getpass.getuser()
    key_type = _ask_text("Remote key type (fills id_<type>.pub)", default=DEFAULT_KEY_TYPE) or DEFAULT_KEY_TYPE
    remote_host = _ask_text("SSH host to connect to", default=host) or host
    ssh_user = _ask_text("SSH login", default=user) or user
    fetch_public_key(
        ssh_dir=ca.ssh_dir,
        host=host,
        user=user,
        remote_host=remote_host,
        ssh_user=ssh_user,
        remote_key=REMOTE_KEY_TEMPLATE.format(key_type=key_type),
        scp=scp,
    )


def action_sign(ca: "SshCa") -> None:
    host = _ask_text("Host label", default=socket.gethostname().split(".")[0])
    if not host:
        return
    user = _ask_text("User id / login", default=getpass.getuser()) or getpass.getuser()
    domain = _ask_text("Domain", default=_default_domain()) or ""
    validity = _ask_text("Validity (ssh-keygen -V)", default=DEFAULT_VALIDITY) or DEFAULT_VALIDITY
    principals = _ask_text("Principals (comma-separated)", default=user) or user
    default_identity = f"{user}@{domain}" if domain else user
    identity = _ask_text("Certificate identity / key id", default=default_identity) or default_identity
    ca.sign(host=host, user=user, identity=identity, principals=principals, validity=validity)


def action_list(ca: "SshCa") -> None:
    certs = list_certs(ca.ssh_dir, ca.ssh_keygen)
    if not certs:
        console.print(f"No certificates ({CERT_SUFFIX}) found in {ca.ssh_dir}.", style="yellow")
        return
    console.print(_render_table(certs))


def action_check(ca: "SshCa") -> None:
    certs = list_certs(ca.ssh_dir, ca.ssh_keygen)
    if not certs:
        console.print(f"No certificates ({CERT_SUFFIX}) found in {ca.ssh_dir}.", style="yellow")
        return
    console.print(_render_table(certs))
    if Xymon is not None and _ask_confirm("Publish expiry status to Xymon?", default=False):
        dry_run = _ask_confirm("Dry-run (echo the command instead of sending)?", default=False)
        _publish_xymon(certs, check_name=XYMON_CHECK_NAME, warn_days=WARN_DAYS, crit_days=CRIT_DAYS, dry_run=dry_run)


_MENU = (
    ("Fetch a public key from a remote host", action_fetch),
    ("Sign / update a certificate", action_sign),
    ("List certificates", action_list),
    ("Check expiry", action_check),
)


def _status_panel(ca: "SshCa") -> Panel:
    def mark(ok: bool) -> str:
        return "[green]ready[/green]" if ok else "[red]missing[/red]"

    count = len(list_certs(ca.ssh_dir, ca.ssh_keygen))
    body = "\n".join(
        (
            f"ssh dir    : [bold]{ca.ssh_dir}[/bold]",
            f"CA key     : {mark(Path(ca.ca_key).is_file())}  ({ca.ca_key})",
            f"ssh-keygen : {ca.ssh_keygen}",
            f"Certs      : {count} certificate(s)",
        )
    )
    return Panel(body, title="SSH Certificate Manager", border_style="cyan", expand=False)


def menu_loop(ca: "SshCa") -> None:
    labels = {label: func for label, func in _MENU}
    quit_label = "Quit"
    while True:
        console.print()
        console.print(_status_panel(ca))
        choice = questionary.select(
            "What would you like to do?",
            choices=[label for label, _ in _MENU] + [questionary.Separator(), quit_label],
        ).ask()
        if choice is None or choice == quit_label:
            break
        action = labels.get(choice)
        if action is None:
            continue
        try:
            action(ca)
        except KeyboardInterrupt:
            console.print("\nInterrupted.", style="yellow")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    help=(
        "Manage SSH user (client) certificates signed by an SSH CA.\n\n"
        "Run without a sub-command for an interactive menu, or use a sub-command "
        "(fetch, sign, list, check) for scripting/non-interactive use."
    ),
)


def _build_ca(ctx: typer.Context) -> SshCa:
    keygen = ctx.obj["ssh_keygen"] or _find_ssh_keygen()
    if not keygen:
        console.print("Could not find the 'ssh-keygen' executable.", style="bold red")
        raise typer.Exit(code=1)
    return SshCa(
        ssh_keygen=keygen,
        ca_key=str(Path(ctx.obj["ca_key"]).expanduser()),
        ssh_dir=str(Path(ctx.obj["ssh_dir"]).expanduser()),
    )


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    ssh_dir: str = typer.Option(DEFAULT_SSH_DIR, "--ssh-dir", help="Directory holding public keys and certificates."),
    ca_key: str = typer.Option(DEFAULT_CA_KEY, "--ca-key", help="Path to the user-CA private key."),
    ssh_keygen: Optional[str] = typer.Option(
        None, "--ssh-keygen", help="Path to ssh-keygen (auto-detected if omitted)."
    ),
) -> None:
    """SSH user certificate manager."""
    ctx.obj = {"ssh_dir": ssh_dir, "ca_key": ca_key, "ssh_keygen": ssh_keygen}

    # A sub-command was requested: let it run, skip the interactive menu.
    if ctx.invoked_subcommand is not None:
        return

    # No sub-command -> interactive menu (needs a real terminal).
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        console.print(
            "ssh-cert-manager's interactive menu needs a real terminal (TTY).\n"
            "Use a sub-command instead (see 'ssh-cert-manager --help').",
            style="bold red",
        )
        raise typer.Exit(code=1)

    ca = _build_ca(ctx)
    console.print(f"Using ssh-keygen: {ca.ssh_keygen}", style="dim")
    try:
        menu_loop(ca)
    except (KeyboardInterrupt, EOFError):
        console.print()
    console.print("Bye.", style="cyan")


@app.command("fetch")
def cmd_fetch(
    ctx: typer.Context,
    host: str = typer.Argument(..., help="Host label, used for the local filename <host>_<user>.pub."),
    user: str = typer.Option(getpass.getuser(), "--user", "-u", help="User id / login (also the local filename part)."),
    key_type: str = typer.Option(DEFAULT_KEY_TYPE, "--key-type", "-t", help="Remote key type (fills id_<type>.pub)."),
    remote_key: Optional[str] = typer.Option(
        None, "--remote-key", help="Full remote public-key path (overrides --key-type)."
    ),
    remote_host: Optional[str] = typer.Option(None, "--remote-host", help="SSH host to connect to (default: <host>)."),
    ssh_user: Optional[str] = typer.Option(None, "--ssh-user", help="Login for the SSH connection (default: <user>)."),
) -> None:
    """Copy a public key from a remote host into the ssh-dir as <host>_<user>.pub."""
    scp = _find_scp()
    if not scp:
        console.print("Could not find the 'scp' executable.", style="bold red")
        raise typer.Exit(code=1)
    resolved_key = remote_key or REMOTE_KEY_TEMPLATE.format(key_type=key_type)
    rc = fetch_public_key(
        ssh_dir=str(Path(ctx.obj["ssh_dir"]).expanduser()),
        host=host,
        user=user,
        remote_host=remote_host or host,
        ssh_user=ssh_user or user,
        remote_key=resolved_key,
        scp=scp,
    )
    raise typer.Exit(code=rc)


@app.command("sign")
def cmd_sign(
    ctx: typer.Context,
    host: Optional[str] = typer.Argument(None, help="Host the key is for (default: local hostname)."),
    user: str = typer.Option(getpass.getuser(), "--user", "-u", help="User id / login."),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Domain for the identity (default: local)."),
    validity: str = typer.Option(DEFAULT_VALIDITY, "--validity", "-V", help="ssh-keygen validity (e.g. +52w)."),
    principals: Optional[str] = typer.Option(None, "--principals", "-n", help="Principals (default: the user)."),
    identity: Optional[str] = typer.Option(
        None, "--identity", "-I", help="Cert identity / key id (default user@domain)."
    ),
) -> None:
    """Create or update (re-sign) a user certificate from <host>_<user>.pub."""
    ca = _build_ca(ctx)
    resolved_host = host or socket.gethostname().split(".")[0]
    resolved_domain = domain if domain is not None else _default_domain()
    resolved_principals = principals or user
    resolved_identity = identity or (f"{user}@{resolved_domain}" if resolved_domain else user)
    rc = ca.sign(
        host=resolved_host,
        user=user,
        identity=resolved_identity,
        principals=resolved_principals,
        validity=validity,
    )
    raise typer.Exit(code=rc)


@app.command("list")
def cmd_list(ctx: typer.Context) -> None:
    """List issued certificates with principals and expiry."""
    ssh_dir = str(Path(ctx.obj["ssh_dir"]).expanduser())
    certs = list_certs(ssh_dir, ctx.obj["ssh_keygen"])
    if not certs:
        console.print(f"No certificates ({CERT_SUFFIX}) found in {ssh_dir}.", style="yellow")
        raise typer.Exit(code=0)
    console.print(_render_table(certs))


@app.command("check")
def cmd_check(
    ctx: typer.Context,
    warn_days: int = typer.Option(WARN_DAYS, "--warn-days", help="Warn if a cert expires within this many days."),
    crit_days: int = typer.Option(CRIT_DAYS, "--crit-days", help="Critical if a cert expires within this many days."),
    xymon: bool = typer.Option(False, "--xymon", help="Also publish the status to Xymon."),
    check_name: str = typer.Option(XYMON_CHECK_NAME, "--check-name", help="Xymon column/test name."),
    dry_run: bool = typer.Option(False, "--dry-run/--send", help="Xymon dry-run: echo instead of sending."),
) -> None:
    """Check certificate expiry. Exit code: 0=ok, 1=warning, 2=critical/expired."""
    global WARN_DAYS, CRIT_DAYS
    WARN_DAYS, CRIT_DAYS = warn_days, crit_days
    ssh_dir = str(Path(ctx.obj["ssh_dir"]).expanduser())
    certs = list_certs(ssh_dir, ctx.obj["ssh_keygen"])
    if not certs:
        console.print(f"No certificates ({CERT_SUFFIX}) found in {ssh_dir}.", style="yellow")
        raise typer.Exit(code=1)
    console.print(_render_table(certs))

    if xymon:
        _publish_xymon(certs, check_name=check_name, warn_days=warn_days, crit_days=crit_days, dry_run=dry_run)

    worst = 0
    for cert in certs:
        days = _days_left(cert)
        if cert.forever:
            continue
        if days is None:
            worst = max(worst, 1)
        elif days < 0 or days <= crit_days:
            worst = max(worst, 2)
        elif days <= warn_days:
            worst = max(worst, 1)
    raise typer.Exit(code=worst)


if __name__ == "__main__":
    app()
