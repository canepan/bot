#!/usr/bin/env python3
"""keepalived-status - parse a ``keepalived.data`` dump and show a readable status.

Keepalived writes a ``keepalived.data`` file when it receives ``SIGUSR1``
(``killall -USR1 keepalived``); the default location is ``/tmp/keepalived.data``.

This tool parses that file and shows:

  * a per-instance table (state, VRID, priority, VIP, tracked-script health,
    last transition);
  * a *distribution* view: which node currently owns each VIP (the local node
    for ``MASTER`` instances, the ``Master router`` for ``BACKUP`` instances);
  * a problems section flagging failing tracked scripts, degraded priorities
    (effective < configured) and instances in ``FAULT``.

Use ``--simple`` for a compact, one-line-per-instance view
(``NAME (VIP): owner (candidate hosts)``); the candidate-host list is read from
the keepalived config files when available.

The path to the data file is configurable (positional argument); it defaults to
``/tmp/keepalived.data``. Pass ``--signal`` to have this tool send ``SIGUSR1``
to the running keepalived first, so the dump is regenerated before it is read
(this usually requires running as root).

Dependencies: click, rich.
"""

import json as _json
import os
import re
import signal
import socket
import subprocess
import time
from glob import glob
from typing import Callable, Dict, List, Optional

import attr
import click
from rich.console import Console
from rich.table import Table

APP_NAME = "keepalived-status"
DEFAULT_DATA_FILE = "/tmp/keepalived.data"

# Where keepalived commonly writes its PID file.
PIDFILE_CANDIDATES = ("/run/keepalived.pid", "/var/run/keepalived.pid")

# Per-instance keepalived config files (used by --simple to list candidate hosts).
KA_CONFIG_DIR = "/etc/keepalived/keepalived.d"

console = Console()

# An indented "Virtual IP" entry, e.g. "    192.168.19.222/24 dev eth0 scope global".
_IP_RE = re.compile(r"^\s+(\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?)\b")

# A bare IPv4 address (no CIDR suffix), used to gate reverse-DNS lookups.
_IP_ONLY_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")

# Human-friendly colours per VRRP state.
_STATE_COLOUR = {
    "MASTER": "bold green",
    "BACKUP": "cyan",
    "FAULT": "bold red",
    "STOP": "dim",
}

_GOOD_STATUSES = {"GOOD", "OK"}


@attr.define
class Script:
    """A tracked VRRP script attached to an instance."""

    name: str
    status: str = "?"
    weight: Optional[int] = None

    @property
    def is_ok(self) -> bool:
        return self.status.upper() in _GOOD_STATUSES


@attr.define
class Instance:
    """A single VRRP instance parsed from ``keepalived.data``."""

    name: str
    state: str = "?"
    vrid: Optional[int] = None
    priority: Optional[int] = None
    effective_priority: Optional[int] = None
    master_router: Optional[str] = None
    master_priority: Optional[int] = None
    last_transition_epoch: Optional[int] = None
    last_transition_human: str = ""
    src_ip: Optional[str] = None
    vips: List[str] = attr.field(factory=list)
    scripts: List[Script] = attr.field(factory=list)

    @property
    def is_master(self) -> bool:
        return self.state.upper() == "MASTER"

    @property
    def is_degraded(self) -> bool:
        """True when a tracked script has lowered the effective priority."""
        return (
            self.effective_priority is not None
            and self.priority is not None
            and self.effective_priority < self.priority
        )

    @property
    def failing_scripts(self) -> List[Script]:
        return [s for s in self.scripts if not s.is_ok]

    @property
    def owner(self) -> str:
        """IP of the node currently holding the VIP for this instance."""
        if self.is_master:
            return self.src_ip or "local"
        return self.master_router or "unknown"


def _to_int(value: str) -> Optional[int]:
    try:
        return int(value.strip().split()[0])
    except (ValueError, IndexError):
        return None


# Type of a function that maps an IP to a short hostname (or returns the IP).
Resolver = Callable[[str], str]


def make_resolver(enabled: bool = True) -> Resolver:
    """Return a cached IP -> short-hostname resolver.

    When ``enabled`` is False (or a lookup fails) the IP is returned unchanged.
    Results are memoised so each IP is looked up at most once.
    """
    cache: Dict[str, str] = {}

    def resolve(ip: str) -> str:
        if not enabled or not _IP_ONLY_RE.match(ip):
            return ip
        if ip not in cache:
            try:
                host = socket.gethostbyaddr(ip)[0]
                cache[ip] = host.split(".")[0] or ip
            except (OSError, socket.herror, socket.gaierror):
                cache[ip] = ip
        return cache[ip]

    return resolve


def _label(ip: str, resolver: Resolver) -> str:
    """Render an IP as "name (ip)" when it resolves, else just the IP."""
    name = resolver(ip)
    return f"{name} ({ip})" if name != ip else ip


def parse(text: str) -> List[Instance]:
    """Parse the textual content of a ``keepalived.data`` file.

    Returns the list of :class:`Instance` in file order.

    >>> data = '''
    ...  VRRP Instance = DNS
    ...    State = BACKUP
    ...    Master router = 192.168.19.132
    ...    Last transition = 1782250831 (Tue Jun 23 22:40:31 2026)
    ...    Using src_ip = 192.168.19.120
    ...    Virtual Router ID = 222
    ...    Priority = 80
    ...  VRRP Script = chk_dns
    ...    Status = GOOD
    ...    Weight = -100
    ...    Virtual IP = 1
    ...      192.168.19.222/24 dev eth0 scope global
    ... '''
    >>> insts = parse(data)
    >>> insts[0].name, insts[0].state, insts[0].vrid, insts[0].vips
    ('DNS', 'BACKUP', 222, ['192.168.19.222/24'])
    >>> insts[0].scripts[0].name, insts[0].scripts[0].status
    ('chk_dns', 'GOOD')
    """
    instances: List[Instance] = []
    cur: Optional[Instance] = None
    cur_script: Optional[Script] = None
    vip_remaining = 0

    for raw in text.splitlines():
        if not raw.strip():
            continue

        # Indented VIP address lines following a "Virtual IP = N" header.
        if vip_remaining > 0 and cur is not None:
            m = _IP_RE.match(raw)
            if m:
                cur.vips.append(m.group(1))
                vip_remaining -= 1
                continue

        stripped = raw.strip()

        if stripped.startswith("VRRP Instance ="):
            cur = Instance(name=stripped.split("=", 1)[1].strip())
            instances.append(cur)
            cur_script = None
            vip_remaining = 0
            continue

        if stripped.startswith("VRRP Script ="):
            if cur is not None:
                cur_script = Script(name=stripped.split("=", 1)[1].strip())
                cur.scripts.append(cur_script)
            continue

        if cur is None:
            continue  # topology header / preamble

        if stripped.startswith("Virtual IP ="):
            vip_remaining = _to_int(stripped.split("=", 1)[1]) or 0
            continue

        if " = " not in stripped:
            continue
        key, value = (p.strip() for p in stripped.split("=", 1))

        # Script-scoped keys take priority while inside a VRRP Script block.
        if cur_script is not None and _apply_script_key(cur_script, key, value):
            continue
        _apply_instance_key(cur, key, value)

    return instances


def _apply_script_key(script: Script, key: str, value: str) -> bool:
    """Apply a key/value to a script; return True if it was a script key."""
    if key == "Status":
        script.status = value
    elif key == "Weight":
        script.weight = _to_int(value)
    else:
        return False
    return True


def _apply_instance_key(inst: Instance, key: str, value: str) -> None:
    """Apply a key/value line to a VRRP instance."""
    if key == "State":
        inst.state = value
    elif key == "Master router":
        inst.master_router = value
    elif key == "Master priority":
        inst.master_priority = _to_int(value)
    elif key == "Virtual Router ID":
        inst.vrid = _to_int(value)
    elif key == "Priority":
        inst.priority = _to_int(value)
    elif key == "Effective priority":
        inst.effective_priority = _to_int(value)
    elif key == "Using src_ip":
        inst.src_ip = value
    elif key == "Last transition":
        inst.last_transition_epoch = _to_int(value)
        human = re.search(r"\((.*)\)", value)
        inst.last_transition_human = human.group(1) if human else value


def _age(epoch: Optional[int]) -> str:
    if not epoch:
        return ""
    delta = int(time.time()) - epoch
    if delta < 0:
        return "in the future"
    for unit, secs in (("d", 86400), ("h", 3600), ("m", 60)):
        if delta >= secs:
            return f"{delta // secs}{unit} ago"
    return f"{delta}s ago"


def _state_text(state: str) -> str:
    colour = _STATE_COLOUR.get(state.upper(), "white")
    return f"[{colour}]{state}[/]"


def _priority_text(inst: Instance) -> str:
    if inst.priority is None:
        return "?"
    if inst.is_degraded:
        return f"[red]{inst.effective_priority}[/] / {inst.priority}"
    return str(inst.priority)


def load_candidate_hosts(config_dir: str = KA_CONFIG_DIR) -> Dict[str, List[str]]:
    """Map VRRP instance name -> configured candidate hosts.

    The candidate-host list is not present in ``keepalived.data``; it is read
    from the per-instance keepalived config files (the ``vrrp`` list in each
    file's JSON header), reusing :class:`simple_service_map.Service`.

    Returns an empty mapping if the config directory or parser is unavailable,
    so callers can degrade gracefully.
    """
    try:
        from tools.bin.simple_service_map import Service
    except Exception:  # pragma: no cover - import guard for non-keepalived hosts
        return {}

    result: Dict[str, List[str]] = {}
    for fname in sorted(glob(os.path.join(config_dir, "*.conf"))):
        try:
            svc = Service(fname)
            hosts = list(svc.hosts)
        except Exception:
            continue
        if hosts:
            result[svc.name] = hosts
    return result


def render_simple(
    instances: List[Instance],
    resolver: Resolver,
    candidate_hosts: Optional[Dict[str, List[str]]] = None,
) -> None:
    """Print one compact line per instance:

    ``NAME (VIP): owner (candidate, hosts)``

    ``owner`` is the short hostname of the node currently holding the VIP
    (``no active host`` when unknown). The parenthesised candidate-host list is
    omitted when it cannot be determined from the keepalived config.
    """
    candidate_hosts = candidate_hosts or {}
    for inst in instances:
        vip = inst.vips[0] if inst.vips else "-"
        owner = "no active host" if inst.owner == "unknown" else resolver(inst.owner)
        hosts = candidate_hosts.get(inst.name)
        suffix = f" ({', '.join(hosts)})" if hosts else ""
        click.echo(f"{inst.name} ({vip}): {owner}{suffix}")


def render(instances: List[Instance], local_ip: Optional[str], resolver: Optional[Resolver] = None) -> None:
    """Render instances to the console as tables.

    ``resolver`` maps an IP to a short hostname (see :func:`make_resolver`);
    when omitted, IPs are shown unchanged.
    """
    if resolver is None:
        resolver = lambda ip: ip  # noqa: E731 - trivial identity default
    if not instances:
        console.print("[yellow]No VRRP instances found in the data file.[/]")
        return

    masters = [i for i in instances if i.is_master]
    backups = [i for i in instances if i.state.upper() == "BACKUP"]
    others = [i for i in instances if i not in masters and i not in backups]

    # ---- Per-instance table -------------------------------------------------
    table = Table(title="Keepalived VRRP instances", header_style="bold")
    table.add_column("Instance")
    table.add_column("State")
    table.add_column("VRID", justify="right")
    table.add_column("Prio (eff/cfg)", justify="right")
    table.add_column("VIP")
    table.add_column("Scripts")
    table.add_column("Last transition")

    for inst in instances:
        if inst.failing_scripts:
            scripts = ", ".join(f"[red]{s.name}={s.status}[/]" for s in inst.failing_scripts)
        elif inst.scripts:
            scripts = "[green]ok[/]"
        else:
            scripts = "[dim]-[/]"
        last = inst.last_transition_human
        age = _age(inst.last_transition_epoch)
        if age:
            last = f"{last} [dim]({age})[/]"
        table.add_row(
            inst.name,
            _state_text(inst.state),
            str(inst.vrid if inst.vrid is not None else "?"),
            _priority_text(inst),
            "\n".join(inst.vips) or "[dim]-[/]",
            scripts,
            last,
        )
    console.print(table)

    # ---- Distribution -------------------------------------------------------
    by_owner: Dict[str, List[Instance]] = {}
    for inst in instances:
        by_owner.setdefault(inst.owner, []).append(inst)

    dist = Table(title="VIP distribution (current owner)", header_style="bold")
    dist.add_column("Node")
    dist.add_column("#", justify="right")
    dist.add_column("Instances")
    for owner in sorted(by_owner):
        label = _label(owner, resolver)
        if local_ip and owner == local_ip:
            label = f"[bold green]{label} (this node)[/]"
        names = sorted(i.name for i in by_owner[owner])
        dist.add_row(label, str(len(names)), ", ".join(names))
    console.print(dist)

    # ---- Summary ------------------------------------------------------------
    summary = (
        f"[bold]{len(instances)}[/] instances: " f"[green]{len(masters)} MASTER[/], " f"[cyan]{len(backups)} BACKUP[/]"
    )
    if others:
        summary += f", [red]{len(others)} other[/]"
    console.print(summary)

    # ---- Problems -----------------------------------------------------------
    problems = _collect_problems(instances)
    if problems:
        console.print("\n[bold underline]Problems[/]")
        for p in problems:
            console.print(f"  {p}")
    else:
        console.print("[green]No problems detected.[/]")


def _collect_problems(instances: List[Instance]) -> List[str]:
    """Return a list of human-readable problem messages for the instances."""
    problems: List[str] = []
    for inst in instances:
        for s in inst.failing_scripts:
            problems.append(f"[red]✗[/] {inst.name}: script [bold]{s.name}[/] is {s.status}")
        if inst.is_degraded:
            problems.append(
                f"[yellow]![/] {inst.name}: priority degraded " f"({inst.effective_priority} < {inst.priority})"
            )
        if inst.state.upper() not in ("MASTER", "BACKUP"):
            problems.append(f"[red]✗[/] {inst.name}: unexpected state {inst.state}")
    return problems


def find_keepalived_pid() -> Optional[int]:
    """Locate the main keepalived process PID.

    Tries the standard PID files first, then falls back to ``pgrep -o`` (the
    oldest matching process, i.e. the parent). Returns ``None`` if not found.
    """
    for pidfile in PIDFILE_CANDIDATES:
        try:
            with open(pidfile) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            continue
    try:
        out = subprocess.check_output(["pgrep", "-o", "keepalived"], universal_newlines=True)
        return int(out.split()[0])
    except (OSError, subprocess.CalledProcessError, ValueError, IndexError):
        return None


def refresh_data_file(path: str, wait: float = 2.0) -> bool:
    """Send ``SIGUSR1`` to keepalived so it (re)writes its data dump.

    Waits up to ``wait`` seconds for ``path`` to be updated. Returns True if the
    signal was delivered (even if the file update was not observed in time),
    False if keepalived could not be found or signalled.
    """
    pid = find_keepalived_pid()
    if pid is None:
        console.print("[red]Could not find a running keepalived process.[/]")
        return False

    try:
        before = os.path.getmtime(path)
    except OSError:
        before = 0.0

    try:
        os.kill(pid, signal.SIGUSR1)
    except PermissionError:
        console.print(
            f"[red]Permission denied sending SIGUSR1 to keepalived (pid {pid}).[/]\n"
            f"  Try: [bold]sudo kill -USR1 {pid}[/]"
        )
        return False
    except OSError as e:
        console.print(f"[red]Failed to signal keepalived (pid {pid}): {e}[/]")
        return False

    deadline = time.time() + wait
    while time.time() < deadline:
        try:
            if os.path.getmtime(path) > before:
                return True
        except OSError:
            pass
        time.sleep(0.1)
    console.print(f"[yellow]Signalled keepalived (pid {pid}); {path} did not update within {wait:g}s.[/]")
    return True


def _to_jsonable(instances: List[Instance], resolver: Resolver) -> list:
    out = []
    for inst in instances:
        d = attr.asdict(inst)
        d["owner"] = inst.owner
        d["owner_name"] = resolver(inst.owner)
        d["is_degraded"] = inst.is_degraded
        out.append(d)
    return out


@click.command(name=APP_NAME)
@click.argument("data_file", default=DEFAULT_DATA_FILE, type=click.Path())
@click.option("--json", "as_json", is_flag=True, help="Emit parsed data as JSON instead of tables.")
@click.option("--no-resolve", "no_resolve", is_flag=True, help="Do not reverse-resolve node IPs to hostnames.")
@click.option(
    "--simple",
    "simple",
    is_flag=True,
    help="One compact line per instance: NAME (VIP): owner (candidate hosts).",
)
@click.option(
    "--signal",
    "-s",
    "do_signal",
    is_flag=True,
    help="Send SIGUSR1 to keepalived to regenerate DATA_FILE before reading it.",
)
def main(data_file: str, as_json: bool, no_resolve: bool, simple: bool, do_signal: bool) -> int:
    """Read DATA_FILE (a keepalived.data dump) and show keepalived status.

    DATA_FILE defaults to /tmp/keepalived.data. With --signal, keepalived is
    asked to regenerate the dump first (usually requires running as root).
    """
    if do_signal and not refresh_data_file(data_file):
        raise SystemExit(1)

    try:
        with open(data_file, "r") as f:
            text = f.read()
    except OSError as e:
        console.print(f"[red]Cannot read {data_file}: {e}[/]")
        raise SystemExit(1)

    instances = parse(text)
    local_ip = next((i.src_ip for i in instances if i.src_ip), None)
    resolver = make_resolver(enabled=not no_resolve)

    if as_json:
        click.echo(_json.dumps(_to_jsonable(instances, resolver), indent=2))
    elif simple:
        render_simple(instances, resolver, load_candidate_hosts())
    else:
        render(instances, local_ip, resolver)
    return 0


if __name__ == "__main__":
    main()
