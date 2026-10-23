#!/usr/bin/env python3
"""List running Docker containers and their associated veth interfaces.

Two methods to find the host-side veth name:

  exec   - `docker exec` into the container to read /sys/class/net/*/iflink.
           Works without host privileges but requires the container to have a
           shell and /sys mounted.
  setns  - Enter the container's network namespace from the host using
           setns(2) on the namespace file referenced by NetworkSettings.SandboxKey,
           then read /sys/class/net directly. No command runs inside the container,
           but requires root or CAP_SYS_ADMIN on the host.
"""

import ctypes
import os
from contextlib import contextmanager

import click
import docker
from rich.console import Console
from rich.table import Table
from rich.text import Text

LIBC = ctypes.CDLL("libc.so.6", use_errno=True)

console = Console()
err_console = Console(stderr=True, style="bold red")


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

    peer_indexes = output[0].decode().split()
    host_ifaces = host_ifindex_map()
    return [host_ifaces[i] for i in peer_indexes if i in host_ifaces]


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

    host_ifaces = host_ifindex_map()
    return [host_ifaces[i] for i in peer_indexes if i in host_ifaces]


@click.command()
@click.option(
    "--method",
    type=click.Choice(["exec", "setns"]),
    default="exec",
    show_default=True,
    help="How to discover veths: exec into containers, or setns from the host.",
)
def main(method: str) -> None:
    client = docker.from_env()
    containers = client.containers.list()

    if not containers:
        console.print("[yellow]No running containers.[/yellow]")
        return

    getter = get_veths_via_exec if method == "exec" else get_veths_via_setns

    table = Table(
        title=f"Running containers ({len(containers)}) — method: {method}",
        title_justify="left",
        show_lines=True,
    )
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("ID", style="magenta", no_wrap=True)
    table.add_column("Image", style="green")
    table.add_column("Veth interfaces", style="yellow")

    for c in containers:
        image = c.image.tags[0] if c.image.tags else c.image.short_id
        net_mode = c.attrs.get("HostConfig", {}).get("NetworkMode", "")
        if net_mode == "host":
            veth_cell = Text("(host network — shares host interfaces)", style="dim")
        else:
            try:
                veths = getter(c)
                if veths:
                    veth_cell = "\n".join(veths)
                else:
                    veth_cell = Text("(none found)", style="dim")
            except PermissionError as e:
                veth_cell = Text(
                    f"{e} — setns needs root/CAP_SYS_ADMIN", style="bold red"
                )
            except (OSError, RuntimeError) as e:
                veth_cell = Text(f"error: {e}", style="bold red")
        table.add_row(c.name, c.short_id, image, veth_cell)

    console.print(table)


if __name__ == "__main__":
    main()
