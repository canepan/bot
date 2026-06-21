#!/usr/bin/env python3
"""vpn-manager - an easy, menu-driven CLI to manage OpenVPN certificates.

A friendly front-end around EasyRSA v3 with nice interactive menus
(``questionary`` for arrow-key selection, ``rich`` for pretty output,
``typer`` for the command-line entry point).

It lets you:
  * initialise a PKI
  * build the CA
  * issue server / client certificates
  * revoke certificates and (re)generate the CRL
  * generate Diffie-Hellman parameters
  * list and inspect certificates
  * bundle a ready-to-use client ``.ovpn`` profile

EasyRSA does the heavy lifting; this tool only orchestrates it and keeps the
workflow safe (confirmations before destructive operations).

Dependencies: typer, questionary, rich  (plus the ``easyrsa`` executable).
"""
import os
import shutil
import subprocess
import sys
import logging
from datetime import datetime, timezone
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

APP_NAME = "vpn-manager"
console = Console()

# Certificates expiring within this many days are flagged as "expiring soon".
WARN_DAYS = 30
# Certificates expiring within this many days are reported as critical (red) to Xymon.
CRIT_DAYS = 7
# Default name for Xymon check
XYMON_CHECK_NAME = "vpncerts"

# Common locations where the easyrsa executable may live.
_EASYRSA_CANDIDATES = (
    "/usr/share/easy-rsa/easyrsa",
    "/usr/local/share/easy-rsa/easyrsa",
    "/opt/homebrew/share/easy-rsa/easyrsa",
    "/usr/local/opt/easy-rsa/share/easy-rsa/easyrsa",
    "/etc/openvpn/easy-rsa/easyrsa",
    "/opt/easy-rsa/easyrsa",
    os.path.expanduser("~/easy-rsa/easyrsa"),
)


def _find_easyrsa() -> Optional[str]:
    """Return the first usable easyrsa executable, or None."""
    on_path = shutil.which("easyrsa")
    if on_path:
        return on_path
    for candidate in _EASYRSA_CANDIDATES:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


@attr.s
class EasyRSA(object):
    """Small wrapper that runs EasyRSA commands against a chosen PKI dir."""

    easyrsa: str = attr.ib()
    pki_dir: str = attr.ib()
    batch: bool = attr.ib(default=False)

    # -- low level ---------------------------------------------------------
    def _env(self) -> dict:
        env = os.environ.copy()
        env["EASYRSA_PKI"] = self.pki_dir
        if self.batch:
            env["EASYRSA_BATCH"] = "1"
        return env

    def run(self, *args: str, check: bool = True) -> int:
        """Run an easyrsa subcommand, streaming its output to the terminal."""
        cmd = [self.easyrsa] + list(args)
        console.print(f"$ EASYRSA_PKI={self.pki_dir} {' '.join(cmd)}", style="dim")
        try:
            result = subprocess.run(cmd, env=self._env())
        except FileNotFoundError:
            console.print(f"EasyRSA executable not found: {self.easyrsa}", style="bold red")
            return 127
        if check and result.returncode != 0:
            console.print(f"Command failed (exit {result.returncode}).", style="bold red")
        return result.returncode

    # -- state helpers -----------------------------------------------------
    @property
    def pki_initialised(self) -> bool:
        return os.path.isdir(os.path.join(self.pki_dir, "issued")) or os.path.isfile(
            os.path.join(self.pki_dir, "openssl-easyrsa.cnf")
        )

    @property
    def ca_built(self) -> bool:
        return os.path.isfile(os.path.join(self.pki_dir, "ca.crt"))

    @property
    def crl_present(self) -> bool:
        return os.path.isfile(os.path.join(self.pki_dir, "crl.pem"))

    @property
    def dh_present(self) -> bool:
        return os.path.isfile(os.path.join(self.pki_dir, "dh.pem"))

    def _list_dir(self, sub: str, suffix: str) -> List[str]:
        path = os.path.join(self.pki_dir, sub)
        if not os.path.isdir(path):
            return []
        return sorted(f[: -len(suffix)] for f in os.listdir(path) if f.endswith(suffix))

    def issued_certs(self) -> List[str]:
        return self._list_dir("issued", ".crt")

    def cert_path(self, name: str) -> str:
        return os.path.join(self.pki_dir, "issued", f"{name}.crt")

    def cert_expiry(self, name: str) -> Optional[datetime]:
        """Return the notAfter date (UTC) of an issued cert, or None if unknown.

        Uses the ``openssl`` CLI; if it is missing or the cert can't be parsed,
        returns None so callers can degrade gracefully.
        """
        path = self.cert_path(name)
        if not os.path.isfile(path) or shutil.which("openssl") is None:
            return None
        try:
            out = subprocess.check_output(
                ["openssl", "x509", "-enddate", "-noout", "-in", path],
                universal_newlines=True,
                stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, OSError):
            return None
        # Format: "notAfter=Jun 10 12:00:00 2027 GMT"
        value = out.strip().split("=", 1)[-1]
        value = value.replace(" GMT", "")
        value = " ".join(value.split())  # normalise padding (e.g. "Jun  9" -> "Jun 9")
        try:
            return datetime.strptime(value, "%b %d %H:%M:%S %Y").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    # -- high level operations --------------------------------------------
    def init_pki(self) -> int:
        return self.run("init-pki")

    def build_ca(self, nopass: bool) -> int:
        args = ["build-ca"]
        if nopass:
            args.append("nopass")
        return self.run(*args)

    def build_server(self, name: str, nopass: bool) -> int:
        args = ["build-server-full", name]
        if nopass:
            args.append("nopass")
        return self.run(*args)

    def build_client(self, name: str, nopass: bool) -> int:
        args = ["build-client-full", name]
        if nopass:
            args.append("nopass")
        return self.run(*args)

    def revoke(self, name: str) -> int:
        return self.run("revoke", name)

    def renew(self, name: str) -> int:
        """Renew an existing certificate (reuses the existing key/request).

        Requires EasyRSA >= 3.0.6. The previous certificate is archived under
        pki/renewed/; regenerate the CRL afterwards to invalidate it.
        """
        return self.run("renew", name)

    def gen_crl(self) -> int:
        return self.run("gen-crl")

    def gen_dh(self) -> int:
        return self.run("gen-dh")

    def show_cert(self, name: str) -> int:
        return self.run("show-cert", name)


# ---------------------------------------------------------------------------
# Small interaction helpers (questionary)
# ---------------------------------------------------------------------------
def _ask_text(message: str, default: str = "") -> Optional[str]:
    answer = questionary.text(message, default=default).ask()
    return answer  # None if the user cancelled (Ctrl-C)


def _ask_confirm(message: str, default: bool = False) -> bool:
    answer = questionary.confirm(message, default=default).ask()
    return bool(answer)


def _require_pki(ersa: "EasyRSA") -> bool:
    if not ersa.pki_initialised:
        console.print(
            f"No PKI found at {ersa.pki_dir}. Initialise it first.", style="yellow"
        )
        return False
    return True


def _require_ca(ersa: "EasyRSA") -> bool:
    if not _require_pki(ersa):
        return False
    if not ersa.ca_built:
        console.print("No CA found. Build the CA first.", style="yellow")
        return False
    return True


def _expiry_status(expiry: Optional[datetime]) -> Tuple[str, str, str]:
    """Map a cert expiry date to (date_text, status_text, rich_style)."""
    if expiry is None:
        return ("unknown", "unknown", "dim")
    days = (expiry - datetime.now(timezone.utc)).days
    date_text = expiry.strftime("%Y-%m-%d")
    if days < 0:
        return (date_text, f"EXPIRED ({-days}d ago)", "bold red")
    if days <= WARN_DAYS:
        return (date_text, f"expiring ({days}d)", "yellow")
    return (date_text, f"valid ({days}d)", "green")


def _render_cert_table(ersa: "EasyRSA") -> Optional[Table]:
    """Build a rich table of issued certs incl. key presence and expiry, or None."""
    certs = ersa.issued_certs()
    if not certs:
        return None
    table = Table(title="Issued certificates", show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Name")
    table.add_column("Key", justify="center")
    table.add_column("Expires")
    table.add_column("Status")
    for idx, name in enumerate(certs, 1):
        has_key = os.path.isfile(os.path.join(ersa.pki_dir, "private", f"{name}.key"))
        date_text, status_text, style = _expiry_status(ersa.cert_expiry(name))
        table.add_row(
            str(idx),
            name,
            "[green]yes[/green]" if has_key else "[yellow]no[/yellow]",
            date_text,
            f"[{style}]{status_text}[/{style}]",
        )
    return table


def _xymon_report(ersa: "EasyRSA", warn_days: int, crit_days: int, check_name: str):
    """Build (XymonStatus, message) describing certificate expiry.

    Overall status is the worst of: red if any cert is expired or within
    ``crit_days``, yellow if any is within ``warn_days`` (or expiry unknown),
    else green. Each line is prefixed with an ``&<color>`` tag so Xymon colours
    it individually.
    """
    severity = {"green": 0, "yellow": 1, "red": 2}
    overall = "green"
    lines = []
    graphs = []
    certs = ersa.issued_certs()
    if not certs:
        return XymonStatus.GREEN, "&green No issued certificates found."
    now = datetime.now(timezone.utc)
    for name in certs:
        expiry = ersa.cert_expiry(name)
        if expiry is None:
            color, detail = "yellow", "expiry unknown"
        else:
            days = (expiry - now).days
            date_text = expiry.strftime("%Y-%m-%d")
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
        lines.append(f"&{color} {name}: {detail}")
        graphs.append(f"{name.replace('.', '_')}.days : {days}")
    status = {"green": XymonStatus.GREEN, "yellow": XymonStatus.YELLOW, "red": XymonStatus.RED}[overall]
    header = f"OpenVPN certificate expiry ({len(certs)} certs, warn<{warn_days}d, crit<{crit_days}d)"
    lines_text = "\n".join(lines)
    graphs_text = "\n".join(graphs)
    return status, f"{header}\n{lines_text}\n\n{graphs_text}"


def _pick_cert(ersa: "EasyRSA", message: str, show_expiry: bool = False) -> Optional[str]:
    certs = ersa.issued_certs()
    if not certs:
        console.print("No issued certificates found.", style="yellow")
        return None
    if show_expiry:
        choices = [
            questionary.Choice(
                title=f"{name} - {_expiry_status(ersa.cert_expiry(name))[1]}",
                value=name,
            )
            for name in certs
        ]
        choices += [questionary.Separator(), questionary.Choice(title="Cancel", value="__cancel__")]
    else:
        choices = certs + [questionary.Separator(), "Cancel"]
    answer = questionary.select(message, choices=choices).ask()
    if not answer or answer in ("Cancel", "__cancel__"):
        return None
    return answer


# ---------------------------------------------------------------------------
# Menu actions
# ---------------------------------------------------------------------------
def action_init_pki(ersa: "EasyRSA") -> None:
    if ersa.pki_initialised:
        console.print(f"A PKI already exists at {ersa.pki_dir}.", style="yellow")
        if not _ask_confirm("Re-initialising DESTROYS all existing keys and certs. Continue?", default=False):
            return
    ersa.init_pki()


def action_build_ca(ersa: "EasyRSA") -> None:
    if not _require_pki(ersa):
        return
    if ersa.ca_built and not _ask_confirm(
        "A CA already exists. Rebuilding it invalidates every issued cert. Continue?", default=False
    ):
        return
    nopass = _ask_confirm("Create the CA key WITHOUT a passphrase?", default=False)
    ersa.build_ca(nopass=nopass)


def action_build_server(ersa: "EasyRSA") -> None:
    if not _require_ca(ersa):
        return
    name = _ask_text("Server certificate name", default="server")
    if not name:
        return
    nopass = _ask_confirm("Create the key without a passphrase? (typical for servers)", default=True)
    ersa.build_server(name=name.strip(), nopass=nopass)


def action_build_client(ersa: "EasyRSA") -> None:
    if not _require_ca(ersa):
        return
    name = _ask_text("Client certificate name")
    if not name or not name.strip():
        console.print("A name is required.", style="red")
        return
    nopass = _ask_confirm("Create the key without a passphrase?", default=True)
    ersa.build_client(name=name.strip(), nopass=nopass)


def action_revoke(ersa: "EasyRSA") -> None:
    if not _require_ca(ersa):
        return
    name = _pick_cert(ersa, "Select a certificate to revoke:", show_expiry=True)
    if not name:
        return
    if not _ask_confirm(f"Really revoke '{name}'? This cannot be undone.", default=False):
        return
    if ersa.revoke(name) == 0:
        console.print("Revoked. Regenerating CRL so the change takes effect...", style="green")
        ersa.gen_crl()


def action_renew(ersa: "EasyRSA") -> None:
    if not _require_ca(ersa):
        return
    name = _pick_cert(ersa, "Select a certificate to renew:", show_expiry=True)
    if not name:
        return
    console.print(
        f"Renew re-signs '{name}' with a new expiry (reusing its existing key). "
        "Requires EasyRSA >= 3.0.6.",
        style="dim",
    )
    if not _ask_confirm(f"Renew '{name}'?", default=True):
        return
    if ersa.renew(name) == 0 and _ask_confirm(
        "Regenerate the CRL now (recommended, invalidates the old certificate)?", default=True
    ):
        ersa.gen_crl()


def action_gen_crl(ersa: "EasyRSA") -> None:
    if _require_ca(ersa):
        ersa.gen_crl()


def action_gen_dh(ersa: "EasyRSA") -> None:
    if _require_pki(ersa):
        console.print("Generating DH parameters can take a while...", style="yellow")
        ersa.gen_dh()


def action_list(ersa: "EasyRSA") -> None:
    if not _require_pki(ersa):
        return
    table = _render_cert_table(ersa)
    if table is None:
        console.print("No issued certificates.", style="yellow")
        return
    console.print(table)


def action_show(ersa: "EasyRSA") -> None:
    if not _require_pki(ersa):
        return
    name = _pick_cert(ersa, "Select a certificate to inspect:", show_expiry=True)
    if name:
        ersa.show_cert(name)


def _publish_xymon(ersa: "EasyRSA", check_name: str, warn_days: int, crit_days: int, dry_run: bool) -> int:
    """Compute the expiry report and send it to the Xymon server.

    Returns 0 on success, non-zero on failure. With ``debug=True`` the Xymon
    helper echoes the command instead of sending (dry-run).
    """
    if Xymon is None or XymonStatus is None:
        console.print(
            "Xymon support is unavailable (could not import tools.libs.xymon).", style="bold red"
        )
        return 2
    status, message = _xymon_report(ersa, warn_days=warn_days, crit_days=crit_days, check_name=check_name)
    if dry_run:
        # Surface what would be sent and let the helper echo the command.
        logging.basicConfig(level=logging.DEBUG)
        console.print(f"[dim]Xymon status:[/dim] {status.value}\n{message}")
    try:
        Xymon(SimpleNamespace(debug=dry_run), APP_NAME, check_name).send_status(status, message, "24h")
    except Exception as exc:  # network/binary errors shouldn't crash the CLI
        console.print(f"Failed to send to Xymon: {exc}", style="bold red")
        return 1
    console.print(f"Published '{check_name}' status to Xymon: {status.value}", style="green")
    return 0


def action_xymon(ersa: "EasyRSA") -> None:
    if not _require_pki(ersa):
        return
    if Xymon is None:
        console.print(
            "Xymon support is unavailable (could not import tools.libs.xymon).", style="bold red"
        )
        return
    status, message = _xymon_report(ersa, warn_days=WARN_DAYS, crit_days=CRIT_DAYS, check_name=XYMON_CHECK_NAME)
    console.print(Panel(message, title=f"Xymon report ({status.value})", border_style="cyan", expand=False))
    debug = _ask_confirm("Dry-run (echo the command instead of sending)?", default=False)
    if not _ask_confirm("Publish this status to Xymon now?", default=True):
        return
    _publish_xymon(ersa, check_name=XYMON_CHECK_NAME, warn_days=WARN_DAYS, crit_days=CRIT_DAYS, debug=debug)


def _write_ovpn(ersa: "EasyRSA", name: str, host: str, port: str, proto: str, out_path: str) -> int:
    """Bundle CA + client cert + key into a single inline .ovpn profile.

    Returns 0 on success, non-zero on failure. Used by both the interactive
    menu and the ``export`` sub-command.
    """
    ca = os.path.join(ersa.pki_dir, "ca.crt")
    crt = os.path.join(ersa.pki_dir, "issued", f"{name}.crt")
    key = os.path.join(ersa.pki_dir, "private", f"{name}.key")
    for path in (ca, crt, key):
        if not os.path.isfile(path):
            console.print(f"Missing required file: {path}", style="red")
            return 1

    def _read(path: str) -> str:
        with open(path) as fh:
            return fh.read().strip()

    profile = (
        "client\n"
        "dev tun\n"
        f"proto {proto}\n"
        f"remote {host} {port}\n"
        "resolv-retry infinite\n"
        "nobind\n"
        "persist-key\n"
        "persist-tun\n"
        "remote-cert-tls server\n"
        "cipher AES-256-GCM\n"
        "auth SHA256\n"
        "verb 3\n"
        f"<ca>\n{_read(ca)}\n</ca>\n"
        f"<cert>\n{_read(crt)}\n</cert>\n"
        f"<key>\n{_read(key)}\n</key>\n"
    )
    try:
        with open(out_path, "w") as fh:
            fh.write(profile)
        os.chmod(out_path, 0o600)
    except OSError as exc:
        console.print(f"Could not write profile: {exc}", style="red")
        return 1
    console.print(
        f"Wrote client profile to {out_path} (contains the private key, keep it safe!).",
        style="green",
    )
    return 0


def action_export_ovpn(ersa: "EasyRSA") -> None:
    """Interactively gather details and export an inline .ovpn profile."""
    if not _require_ca(ersa):
        return
    name = _pick_cert(ersa, "Select a client certificate to export:")
    if not name:
        return
    server_host = _ask_text("VPN server hostname/IP", default="vpn.example.com")
    if server_host is None:
        return
    server_port = _ask_text("VPN server port", default="1194")
    if server_port is None:
        return
    proto = questionary.select("Protocol", choices=["udp", "tcp"]).ask()
    if proto is None:
        return
    out_path = _ask_text("Output file", default=os.path.join(os.getcwd(), f"{name}.ovpn"))
    if not out_path:
        return
    _write_ovpn(ersa, name=name, host=server_host, port=server_port, proto=proto, out_path=out_path)


# ---------------------------------------------------------------------------
# Menu wiring
# ---------------------------------------------------------------------------
_MENU = (
    ("Initialise PKI", action_init_pki),
    ("Build CA", action_build_ca),
    ("Build server certificate", action_build_server),
    ("Build client certificate", action_build_client),
    ("Revoke a certificate", action_revoke),
    ("Renew a certificate", action_renew),
    ("Generate CRL", action_gen_crl),
    ("Generate DH parameters", action_gen_dh),
    ("List certificates", action_list),
    ("Show certificate details", action_show),
    ("Publish expiry status to Xymon", action_xymon),
    ("Export client .ovpn profile", action_export_ovpn),
)


def _status_panel(ersa: "EasyRSA") -> Panel:
    def mark(ok: bool) -> str:
        return "[green]ready[/green]" if ok else "[red]missing[/red]"

    body = "\n".join(
        (
            f"PKI dir : [bold]{ersa.pki_dir}[/bold]",
            f"easyrsa : {ersa.easyrsa}",
            f"PKI     : {mark(ersa.pki_initialised)}",
            f"CA      : {mark(ersa.ca_built)}",
            f"CRL     : {mark(ersa.crl_present)}",
            f"DH      : {mark(ersa.dh_present)}",
            f"Issued  : {len(ersa.issued_certs())} certificate(s)",
        )
    )
    return Panel(body, title="OpenVPN Certificate Manager", border_style="cyan", expand=False)


def menu_loop(ersa: "EasyRSA") -> None:
    labels = {label: func for label, func in _MENU}
    quit_label = "Quit"
    while True:
        console.print()
        console.print(_status_panel(ersa))
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
            action(ersa)
        except KeyboardInterrupt:
            console.print("\nInterrupted.", style="yellow")


# ---------------------------------------------------------------------------
# Entry point (typer)
# ---------------------------------------------------------------------------
app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    help=(
        "Manage OpenVPN certificates with EasyRSA.\n\n"
        "Run without a sub-command for an interactive menu, or use a sub-command "
        "(init-pki, build-ca, build-server, ...) for scripting/non-interactive use."
    ),
)


def _build_ersa(ctx: typer.Context) -> "EasyRSA":
    """Resolve easyrsa + PKI dir from the shared callback options."""
    pki_dir, easyrsa, batch = ctx.obj["pki_dir"], ctx.obj["easyrsa"], ctx.obj["batch"]
    resolved = easyrsa or _find_easyrsa()
    if not resolved:
        console.print(
            "Could not find the 'easyrsa' executable.\n"
            "Install EasyRSA (e.g. 'brew install easy-rsa' or your distro package) "
            "or pass --easyrsa /path/to/easyrsa.",
            style="bold red",
        )
        raise typer.Exit(code=1)
    return EasyRSA(easyrsa=resolved, pki_dir=os.path.abspath(pki_dir), batch=batch)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    pki_dir: str = typer.Option(
        os.path.join(os.getcwd(), "pki"),
        "--pki-dir",
        help="Directory holding (or to hold) the PKI.",
    ),
    easyrsa: Optional[str] = typer.Option(
        None, "--easyrsa", help="Path to the easyrsa executable (auto-detected if omitted)."
    ),
    batch: bool = typer.Option(False, "--batch", help="Run EasyRSA non-interactively where possible."),
) -> None:
    """OpenVPN certificate manager (EasyRSA backend)."""
    ctx.obj = {"pki_dir": pki_dir, "easyrsa": easyrsa, "batch": batch}

    # A sub-command was requested: let it run, skip the interactive menu.
    if ctx.invoked_subcommand is not None:
        return

    # No sub-command -> interactive menu (needs a real terminal).
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        console.print(
            "vpn-manager's interactive menu needs a real terminal (TTY).\n"
            "Use a sub-command instead (see 'vpn-manager --help').",
            style="bold red",
        )
        raise typer.Exit(code=1)

    ersa = _build_ersa(ctx)
    console.print(f"Using easyrsa: {ersa.easyrsa}", style="dim")
    try:
        menu_loop(ersa)
    except (KeyboardInterrupt, EOFError):
        console.print()
    console.print("Bye.", style="cyan")


# -- non-interactive sub-commands ------------------------------------------
@app.command("init-pki")
def cmd_init_pki(ctx: typer.Context) -> None:
    """Initialise a fresh PKI."""
    raise typer.Exit(code=_build_ersa(ctx).init_pki())


@app.command("build-ca")
def cmd_build_ca(
    ctx: typer.Context,
    nopass: bool = typer.Option(False, "--nopass", help="Create the CA key without a passphrase."),
) -> None:
    """Build the Certificate Authority."""
    raise typer.Exit(code=_build_ersa(ctx).build_ca(nopass=nopass))


@app.command("build-server")
def cmd_build_server(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Server certificate name."),
    nopass: bool = typer.Option(True, "--nopass/--pass", help="Create the key without a passphrase."),
) -> None:
    """Issue a server certificate."""
    raise typer.Exit(code=_build_ersa(ctx).build_server(name=name, nopass=nopass))


@app.command("build-client")
def cmd_build_client(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Client certificate name."),
    nopass: bool = typer.Option(True, "--nopass/--pass", help="Create the key without a passphrase."),
) -> None:
    """Issue a client certificate."""
    raise typer.Exit(code=_build_ersa(ctx).build_client(name=name, nopass=nopass))


@app.command("revoke")
def cmd_revoke(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Certificate name to revoke."),
    gen_crl: bool = typer.Option(True, "--gen-crl/--no-gen-crl", help="Regenerate the CRL after revoking."),
) -> None:
    """Revoke a certificate (and regenerate the CRL by default)."""
    ersa = _build_ersa(ctx)
    rc = ersa.revoke(name)
    if rc == 0 and gen_crl:
        rc = ersa.gen_crl()
    raise typer.Exit(code=rc)


@app.command("renew")
def cmd_renew(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Certificate name to renew."),
    gen_crl: bool = typer.Option(True, "--gen-crl/--no-gen-crl", help="Regenerate the CRL after renewing."),
) -> None:
    """Renew a certificate, reusing its key (EasyRSA >= 3.0.6)."""
    ersa = _build_ersa(ctx)
    rc = ersa.renew(name)
    if rc == 0 and gen_crl:
        rc = ersa.gen_crl()
    raise typer.Exit(code=rc)


@app.command("gen-crl")
def cmd_gen_crl(ctx: typer.Context) -> None:
    """Generate the Certificate Revocation List."""
    raise typer.Exit(code=_build_ersa(ctx).gen_crl())


@app.command("gen-dh")
def cmd_gen_dh(ctx: typer.Context) -> None:
    """Generate Diffie-Hellman parameters."""
    raise typer.Exit(code=_build_ersa(ctx).gen_dh())


@app.command("list")
def cmd_list(ctx: typer.Context) -> None:
    """List issued certificates with key presence and expiry status."""
    ersa = _build_ersa(ctx)
    table = _render_cert_table(ersa)
    if table is None:
        console.print("No issued certificates.", style="yellow")
        return
    console.print(table)


@app.command("show")
def cmd_show(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Certificate name to inspect."),
) -> None:
    """Show details of a certificate."""
    raise typer.Exit(code=_build_ersa(ctx).show_cert(name))


@app.command("xymon")
def cmd_xymon(
    ctx: typer.Context,
    check_name: str = typer.Option(XYMON_CHECK_NAME, "--check-name", help="Xymon column/test name."),
    warn_days: int = typer.Option(WARN_DAYS, "--warn-days", help="Yellow if a cert expires within this many days."),
    crit_days: int = typer.Option(CRIT_DAYS, "--crit-days", help="Red if a cert expires within this many days."),
    dry_run: bool = typer.Option(False, "--dry-run/--send", help="Dry-run: echo the command instead of sending."),
) -> None:
    """Publish certificate expiry status to Xymon (suited for cron).

    Sends to the servers in $XYMONSERVERS using the 'xymon' client binary.
    """
    rc = _publish_xymon(
        _build_ersa(ctx), check_name=check_name, warn_days=warn_days, crit_days=crit_days, dry_run=dry_run
    )
    raise typer.Exit(code=rc)


@app.command("export")
def cmd_export(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Client certificate name to export."),
    host: str = typer.Option("vpn.example.com", "--host", help="VPN server hostname/IP."),
    port: int = typer.Option(1194, "--port", help="VPN server port."),
    proto: str = typer.Option("udp", "--proto", help="Protocol: udp or tcp."),
    out: Optional[str] = typer.Option(None, "--out", help="Output .ovpn path (default: ./<name>.ovpn)."),
) -> None:
    """Export an inline .ovpn client profile (CA + cert + key)."""
    ersa = _build_ersa(ctx)
    out_path = out or os.path.join(os.getcwd(), "{name}.ovpn")
    rc = _write_ovpn(ersa, name=name, host=host, port=str(port), proto=proto, out_path=out_path)
    raise typer.Exit(code=rc)


if __name__ == "__main__":
    app()
