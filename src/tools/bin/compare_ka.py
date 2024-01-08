#!/usr/bin/env python3
from subprocess import check_output, CalledProcessError, STDOUT

import attr
import click

from tools.bin.simple_service_map import HostChecker
from tools.libs.net_utils import hosts_if_not_me


@click.command()
@click.argument("hostnames", nargs=-1) #, type=set)
def main(hostnames: set):
    hc = HostChecker(hostnames)
    for host in hosts_if_not_me(hc.hosts):
        click.echo(f"Checking {host.name}...")
        click.echo(check_output(["remote_diff.sh", "/etc/keepalived/keepalived.d/", f"{host.name}:/etc/keepalived/keepalived.d/"], universal_newlines=True, stderr=STDOUT))


if __name__ == "__main__":
    main()
