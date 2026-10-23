#!/usr/bin/env python3
"""List running Docker containers, their veth interfaces, and network traffic.

Discovery methods for the host-side veth name:

  exec   - `docker exec` into the container to read /sys/class/net/*/iflink.
           Works without host privileges but requires the container to have a
           shell and /sys mounted.
  setns  - Enter the container's network namespace from the host using
           setns(2) on the namespace file referenced by NetworkSettings.SandboxKey,
           then read /sys/class/net directly. No command runs inside the container,
           but requires root or CAP_SYS_ADMIN on the host.

Traffic counters are read from /sys/class/net/<veth>/statistics on the host.
RX/TX are from the host interface's point of view: RX is traffic the container
sent, TX is traffic delivered to the container.
"""

import ctypes
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

import click
import docker
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

LIBC = ctypes.CDLL("libc.so.6", use_errno=True)

console = Console()


@dataclass
class ContainerInfo:
    name: str
    short_id: str
    image: str
    veths: list[str] = field(default_factory=list)
    note: str | None = None  # e.g. host network or an error message


@contextmanager
def network_namespace(nspath: str):
    """Enter the given network namespace, then restore the original."""
    self_ns = os.open("/proc/self/ns/net", os.O_RDONLY)
    target_ns = os.open(nspath, os.O_RDONLY)
    try:
        if LIBC.setns(target_ns, 0) != 0:
            err = ctypes.get_errno()
            raise OSError(err, f"setns failed: {os.strerror(err)}")
        yield
    finally:
        LIBC.setns(self_ns, 0)
        os.close(self_ns)
        os.close(target_ns)


def host_ifindex_map() -> dict[str, str]:
    """Build ifindex -> interface name map for the host."""
    ifaces = {}
    for iface in os.listdir("/sys/class/net"):
        try:
            with open(f"/sys/class/net/{iface}/ifindex") as f:
                ifaces[f.read().strip()] = iface
        except OSError:
            continue
    return ifaces


def resolve_peer_names(peer_indexes: list[str]) -> list[str]:
    host_ifaces = host_ifindex_map()
    return [host_ifaces[i] for i in peer_indexes if i in host_ifaces]


def get_veths_via_exec(container) -> list[str]:
    """Find veths by exec'ing into the container."""
    try:
        exit_code, output = container.exec_run(
            ["sh", "-c", "ls -d /sys/class/net/*/ | grep -v '/lo/' | "
             "xargs -n1 -I{} sh -c 'cat {}iflink'"],
            demux=True,
        )
    except docker.errors.APIError as e:
        raise RuntimeError(f"could not exec in container: {e}") from e

    if exit_code != 0 or output[0] is None:
        return []

    return resolve_peer_names(output[0].decode().split())


def get_veths_via_setns(container) -> list[str]:
    """Find veths by entering the container's netns from the host via setns."""
    container.reload()
    nspath = container.attrs.get("NetworkSettings", {}).get("SandboxKey")
    if not nspath:
        return []

    peer_indexes = []
    with network_namespace(nspath):
        for iface in os.listdir("/sys/class/net"):
            if iface == "lo":
                continue
            try:
                with open(f"/sys/class/net/{iface}/iflink") as f:
                    peer_indexes.append(f.read().strip())
            except OSError:
                continue

    return resolve_peer_names(peer_indexes)


def read_stats(iface: str) -> dict[str, int] | None:
    """Read rx/tx byte counters for a host interface. None if it vanished."""
    stats = {}
    try:
        for key in ("rx_bytes", "tx_bytes"):
            with open(f"/sys/class/net/{iface}/statistics/{key}") as f:
                stats[key] = int(f.read().strip())
    except (OSError, ValueError):
        return None
    return stats


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def collect_containers(client, getter) -> list[ContainerInfo]:
    """Resolve running containers and their veths."""
    infos = []
    for c in client.containers.list():
        image = c.image.tags[0] if c.image.tags else c.image.short_id
        info = ContainerInfo(name=c.name, short_id=c.short_id, image=image)

        net_mode = c.attrs.get("HostConfig", {}).get("NetworkMode", "")
        if net_mode == "host":
            info.note = "host network — shares host interfaces"
        else:
            try:
                info.veths = getter(c)
                if not info.veths:
                    info.note = "no veths found"
            except PermissionError as e:
                info.note = f"{e} — setns needs root/CAP_SYS_ADMIN"
            except (OSError, RuntimeError) as e:
                info.note = f"error: {e}"
        infos.append(info)
    return infos


def build_table(
    infos: list[ContainerInfo],
    method: str,
    prev_stats: dict[str, tuple[float, dict[str, int]]] | None = None,
) -> tuple[Table, dict[str, tuple[float, dict[str, int]]]]:
    """Build the display table; returns it plus the fresh stats snapshot.

    If prev_stats is given, cells show per-second rates; otherwise cumulative
    counters since boot.
    """
    now = time.monotonic()
    fresh: dict[str, tuple[float, dict[str, int]]] = {}

    watch = prev_stats is not None
    title = f"Running containers ({len(infos)}) — method: {method}"
    if watch:
        title += " — live rates (Ctrl-C to stop)"

    table = Table(title=title, title_justify="left", show_lines=True)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("ID", style="magenta", no_wrap=True)
    table.add_column("Image", style="green")
    table.add_column("Veth / traffic", style="yellow")

    for info in infos:
        if info.note is not None:
            cell: str | Text = Text(f"({info.note})", style="dim")
        else:
            lines = []
            for veth in info.veths:
                stats = read_stats(veth)
                if stats is None:
                    lines.append(Text(f"{veth}  (interface gone)", style="dim"))
                    continue
                fresh[veth] = (now, stats)
                if watch:
                    prev = prev_stats.get(veth)
                    if prev is None:
                        lines.append(Text(f"{veth}  measuring…", style="dim"))
                        continue
                    dt = now - prev[0]
                    rx_rate = (stats["rx_bytes"] - prev[1]["rx_bytes"]) / dt
                    tx_rate = (stats["tx_bytes"] - prev[1]["tx_bytes"]) / dt
                    lines.append(
                        Text.assemble(
                            (f"{veth}  ", "bold"),
                            (f"↓ {human_bytes(rx_rate)}/s", "bright_blue"),
                            ("  ", ""),
                            (f"↑ {human_bytes(tx_rate)}/s", "bright_magenta"),
                        )
                    )
                else:
                    lines.append(
                        Text.assemble(
                            (f"{veth}  ", "bold"),
                            (f"↓ {human_bytes(stats['rx_bytes'])}", "bright_blue"),
                            ("  ", ""),
                            (f"↑ {human_bytes(stats['tx_bytes'])}", "bright_magenta"),
                        )
                    )
            cell = Text("\n").join(lines) if lines else Text("(no veths)", style="dim")
        table.add_row(info.name, info.short_id, info.image, cell)

    return table, fresh


@click.command()
@click.option(
    "--method",
    type=click.Choice(["exec", "setns"]),
    default="exec",
    show_default=True,
    help="How to discover veths: exec into containers, or setns from the host.",
)
@click.option(
    "--watch",
    "watch_interval",
    type=click.FloatRange(min=0.5),
    default=None,
    metavar="SECONDS",
    help="Refresh continuously, showing per-second traffic rates.",
)
def main(method: str, watch_interval: float | None) -> None:
    client = docker.from_env()
    getter = get_veths_via_exec if method == "exec" else get_veths_via_setns

    if watch_interval is None:
        infos = collect_containers(client, getter)
        if not infos:
            console.print("[yellow]No running containers.[/yellow]")
            return
        table, _ = build_table(infos, method)
        console.print(table)
        return

    # Watch mode: first sample establishes the baseline, then render rates.
    prev: dict[str, tuple[float, dict[str, int]]] = {}
    with Live(console=console, refresh_per_second=4) as live:
        try:
            while True:
                infos = collect_containers(client, getter)
                table, prev = build_table(infos, method, prev_stats=prev)
                live.update(table)
                time.sleep(watch_interval)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
