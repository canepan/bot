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
import sys
from contextlib import contextmanager

import click
import docker

LIBC = ctypes.CDLL("libc.so.6", use_errno=True)


@contextmanager
def network_namespace(nspath: str):
    """Enter the given network namespace, then restore the original."""
    # Save current namespace
    self_ns = os.open("/proc/self/ns/net", os.O_RDONLY)
    target_ns = os.open(nspath, os.O_RDONLY)
    try:
        if LIBC.setns(target_ns, 0) != 0:
            err = ctypes.get_errno()
            raise OSError(err, f"setns failed: {os.strerror(err)}")
        yield
    finally:
        # Always restore original namespace
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
        print(f"  (could not exec in container: {e})", file=sys.stderr)
        return []

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

    # Read iflinks from inside the container's netns
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

    # Resolve against host interfaces (we are back in the host netns here)
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
        print("No running containers.")
        return

    getter = get_veths_via_exec if method == "exec" else get_veths_via_setns

    for c in containers:
        name = c.name
        short_id = c.short_id
        image = c.image.tags[0] if c.image.tags else c.image.short_id
        print(f"{name} ({short_id}) [{image}]")
        try:
            veths = getter(c)
        except PermissionError as e:
            print(f"  error: {e} (setns method requires root or CAP_SYS_ADMIN)")
            continue
        except OSError as e:
            print(f"  error: {e}")
            continue
        if veths:
            for v in veths:
                print(f"  veth: {v}")
        else:
            print("  veth: (none found - may use host/network-none mode)")


if __name__ == "__main__":
    main()
