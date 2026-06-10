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
from typing import List, Optional

import attr
import questionary
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

APP_NAME = "vpn-manager"
console = Console()

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
        console.print("$ EASYRSA_PKI={} {}".format(self.pki_dir, " ".join(cmd)), style="dim")
        try:
            result = subprocess.run(cmd, env=self._env())
        except FileNotFoundError:
            console.print("EasyRSA executable not found: {}".format(self.easyrsa), style="bold red")
            return 127
        if check and result.returncode != 0:
            console.print("Command failed (exit {}).".format(result.returncode), style="bold red")
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


def _require_pki(era: "EasyRSA") -> bool:
    if not era.pki_initialised:
        console.print(
            "No PKI found at {}. Initialise it first.".format(era.pki_dir), style="yellow"
        )
        return False
    return True


def _require_ca(era: "EasyRSA") -> bool:
    if not _require_pki(era):
        return False
    if not era.ca_built:
        console.print("No CA found. Build the CA first.", style="yellow")
        return False
    return True


def _pick_cert(era: "EasyRSA", message: str) -> Optional[str]:
    certs = era.issued_certs()
    if not certs:
        console.print("No issued certificates found.", style="yellow")
        return None
    choices = certs + [questionary.Separator(), "Cancel"]
    answer = questionary.select(message, choices=choices).ask()
    if not answer or answer == "Cancel":
        return None
    return answer


# ---------------------------------------------------------------------------
# Menu actions
# ---------------------------------------------------------------------------
def action_init_pki(era: "EasyRSA") -> None:
    if era.pki_initialised:
        console.print("A PKI already exists at {}.".format(era.pki_dir), style="yellow")
        if not _ask_confirm("Re-initialising DESTROYS all existing keys and certs. Continue?", default=False):
            return
    era.init_pki()


def action_build_ca(era: "EasyRSA") -> None:
    if not _require_pki(era):
        return
    if era.ca_built and not _ask_confirm(
        "A CA already exists. Rebuilding it invalidates every issued cert. Continue?", default=False
    ):
        return
    nopass = _ask_confirm("Create the CA key WITHOUT a passphrase?", default=False)
    era.build_ca(nopass=nopass)


def action_build_server(era: "EasyRSA") -> None:
    if not _require_ca(era):
        return
    name = _ask_text("Server certificate name", default="server")
    if not name:
        return
    nopass = _ask_confirm("Create the key without a passphrase? (typical for servers)", default=True)
    era.build_server(name=name.strip(), nopass=nopass)


def action_build_client(era: "EasyRSA") -> None:
    if not _require_ca(era):
        return
    name = _ask_text("Client certificate name")
    if not name or not name.strip():
        console.print("A name is required.", style="red")
        return
    nopass = _ask_confirm("Create the key without a passphrase?", default=True)
    era.build_client(name=name.strip(), nopass=nopass)


def action_revoke(era: "EasyRSA") -> None:
    if not _require_ca(era):
        return
    name = _pick_cert(era, "Select a certificate to revoke:")
    if not name:
        return
    if not _ask_confirm("Really revoke '{}'? This cannot be undone.".format(name), default=False):
        return
    if era.revoke(name) == 0:
        console.print("Revoked. Regenerating CRL so the change takes effect...", style="green")
        era.gen_crl()


def action_gen_crl(era: "EasyRSA") -> None:
    if _require_ca(era):
        era.gen_crl()


def action_gen_dh(era: "EasyRSA") -> None:
    if _require_pki(era):
        console.print("Generating DH parameters can take a while...", style="yellow")
        era.gen_dh()


def action_list(era: "EasyRSA") -> None:
    if not _require_pki(era):
        return
    certs = era.issued_certs()
    if not certs:
        console.print("No issued certificates.", style="yellow")
        return
    table = Table(title="Issued certificates", show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Name")
    table.add_column("Has private key", justify="center")
    for idx, name in enumerate(certs, 1):
        has_key = os.path.isfile(os.path.join(era.pki_dir, "private", "{}.key".format(name)))
        table.add_row(str(idx), name, "[green]yes[/green]" if has_key else "[yellow]no[/yellow]")
    console.print(table)


def action_show(era: "EasyRSA") -> None:
    if not _require_pki(era):
        return
    name = _pick_cert(era, "Select a certificate to inspect:")
    if name:
        era.show_cert(name)


def _write_ovpn(era: "EasyRSA", name: str, host: str, port: str, proto: str, out_path: str) -> int:
    """Bundle CA + client cert + key into a single inline .ovpn profile.

    Returns 0 on success, non-zero on failure. Used by both the interactive
    menu and the ``export`` sub-command.
    """
    ca = os.path.join(era.pki_dir, "ca.crt")
    crt = os.path.join(era.pki_dir, "issued", "{}.crt".format(name))
    key = os.path.join(era.pki_dir, "private", "{}.key".format(name))
    for path in (ca, crt, key):
        if not os.path.isfile(path):
            console.print("Missing required file: {}".format(path), style="red")
            return 1

    def _read(path: str) -> str:
        with open(path) as fh:
            return fh.read().strip()

    profile = (
        "client\n"
        "dev tun\n"
        "proto {proto}\n"
        "remote {host} {port}\n"
        "resolv-retry infinite\n"
        "nobind\n"
        "persist-key\n"
        "persist-tun\n"
        "remote-cert-tls server\n"
        "cipher AES-256-GCM\n"
        "auth SHA256\n"
        "verb 3\n"
        "<ca>\n{ca}\n</ca>\n"
        "<cert>\n{cert}\n</cert>\n"
        "<key>\n{key}\n</key>\n"
    ).format(
        proto=proto,
        host=host,
        port=port,
        ca=_read(ca),
        cert=_read(crt),
        key=_read(key),
    )
    try:
        with open(out_path, "w") as fh:
            fh.write(profile)
        os.chmod(out_path, 0o600)
    except OSError as exc:
        console.print("Could not write profile: {}".format(exc), style="red")
        return 1
    console.print(
        "Wrote client profile to {} (contains the private key, keep it safe!).".format(out_path),
        style="green",
    )
    return 0


def action_export_ovpn(era: "EasyRSA") -> None:
    """Interactively gather details and export an inline .ovpn profile."""
    if not _require_ca(era):
        return
    name = _pick_cert(era, "Select a client certificate to export:")
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
    out_path = _ask_text("Output file", default=os.path.join(os.getcwd(), "{}.ovpn".format(name)))
    if not out_path:
        return
    _write_ovpn(era, name=name, host=server_host, port=server_port, proto=proto, out_path=out_path)


# ---------------------------------------------------------------------------
# Menu wiring
# ---------------------------------------------------------------------------
_MENU = (
    ("Initialise PKI", action_init_pki),
    ("Build CA", action_build_ca),
    ("Build server certificate", action_build_server),
    ("Build client certificate", action_build_client),
    ("Revoke a certificate", action_revoke),
    ("Generate CRL", action_gen_crl),
    ("Generate DH parameters", action_gen_dh),
    ("List certificates", action_list),
    ("Show certificate details", action_show),
    ("Export client .ovpn profile", action_export_ovpn),
)


def _status_panel(era: "EasyRSA") -> Panel:
    def mark(ok: bool) -> str:
        return "[green]ready[/green]" if ok else "[red]missing[/red]"

    body = (
        "PKI dir : [bold]{dir}[/bold]\n"
        "easyrsa : {bin}\n"
        "PKI     : {pki}\n"
        "CA      : {ca}\n"
        "CRL     : {crl}\n"
        "DH      : {dh}\n"
        "Issued  : {n} certificate(s)"
    ).format(
        dir=era.pki_dir,
        bin=era.easyrsa,
        pki=mark(era.pki_initialised),
        ca=mark(era.ca_built),
        crl=mark(era.crl_present),
        dh=mark(era.dh_present),
        n=len(era.issued_certs()),
    )
    return Panel(body, title="OpenVPN Certificate Manager", border_style="cyan", expand=False)


def menu_loop(era: "EasyRSA") -> None:
    labels = {label: func for label, func in _MENU}
    quit_label = "Quit"
    while True:
        console.print()
        console.print(_status_panel(era))
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
            action(era)
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


def _build_era(ctx: typer.Context) -> "EasyRSA":
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

    era = _build_era(ctx)
    console.print("Using easyrsa: {}".format(era.easyrsa), style="dim")
    try:
        menu_loop(era)
    except (KeyboardInterrupt, EOFError):
        console.print()
    console.print("Bye.", style="cyan")


# -- non-interactive sub-commands ------------------------------------------
@app.command("init-pki")
def cmd_init_pki(ctx: typer.Context) -> None:
    """Initialise a fresh PKI."""
    raise typer.Exit(code=_build_era(ctx).init_pki())


@app.command("build-ca")
def cmd_build_ca(
    ctx: typer.Context,
    nopass: bool = typer.Option(False, "--nopass", help="Create the CA key without a passphrase."),
) -> None:
    """Build the Certificate Authority."""
    raise typer.Exit(code=_build_era(ctx).build_ca(nopass=nopass))


@app.command("build-server")
def cmd_build_server(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Server certificate name."),
    nopass: bool = typer.Option(True, "--nopass/--pass", help="Create the key without a passphrase."),
) -> None:
    """Issue a server certificate."""
    raise typer.Exit(code=_build_era(ctx).build_server(name=name, nopass=nopass))


@app.command("build-client")
def cmd_build_client(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Client certificate name."),
    nopass: bool = typer.Option(True, "--nopass/--pass", help="Create the key without a passphrase."),
) -> None:
    """Issue a client certificate."""
    raise typer.Exit(code=_build_era(ctx).build_client(name=name, nopass=nopass))


@app.command("revoke")
def cmd_revoke(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Certificate name to revoke."),
    gen_crl: bool = typer.Option(True, "--gen-crl/--no-gen-crl", help="Regenerate the CRL after revoking."),
) -> None:
    """Revoke a certificate (and regenerate the CRL by default)."""
    era = _build_era(ctx)
    rc = era.revoke(name)
    if rc == 0 and gen_crl:
        rc = era.gen_crl()
    raise typer.Exit(code=rc)


@app.command("gen-crl")
def cmd_gen_crl(ctx: typer.Context) -> None:
    """Generate the Certificate Revocation List."""
    raise typer.Exit(code=_build_era(ctx).gen_crl())


@app.command("gen-dh")
def cmd_gen_dh(ctx: typer.Context) -> None:
    """Generate Diffie-Hellman parameters."""
    raise typer.Exit(code=_build_era(ctx).gen_dh())


@app.command("list")
def cmd_list(ctx: typer.Context) -> None:
    """List issued certificates."""
    era = _build_era(ctx)
    certs = era.issued_certs()
    if not certs:
        console.print("No issued certificates.", style="yellow")
        return
    table = Table(title="Issued certificates", show_header=True, header_style="bold cyan")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Name")
    table.add_column("Has private key", justify="center")
    for idx, name in enumerate(certs, 1):
        has_key = os.path.isfile(os.path.join(era.pki_dir, "private", "{}.key".format(name)))
        table.add_row(str(idx), name, "[green]yes[/green]" if has_key else "[yellow]no[/yellow]")
    console.print(table)


@app.command("show")
def cmd_show(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Certificate name to inspect."),
) -> None:
    """Show details of a certificate."""
    raise typer.Exit(code=_build_era(ctx).show_cert(name))


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
    era = _build_era(ctx)
    out_path = out or os.path.join(os.getcwd(), "{}.ovpn".format(name))
    rc = _write_ovpn(era, name=name, host=host, port=str(port), proto=proto, out_path=out_path)
    raise typer.Exit(code=rc)


if __name__ == "__main__":
    app()
