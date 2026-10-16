#!/usr/bin/env python3
import attrs
import click
from subprocess import check_output


@attrs.define
class MacAddress(object):
    ip: str
    mac: str

    @classmethod
    def from_arp_command(cls, line: str) -> "MacAddress":
        return cls(*line.replace("(", "").replace(")", "").split()[1:4:2])


def get_mac_addresses(filter: str) -> list:
    cmd = ["arp", "-na"]
    return [MacAddress.from_arp_command(line) for line in check_output(cmd, universal_newlines=True).splitlines() if "incomplete" not in line and re.search(filter, line)]


def is_local(ip: str) -> bool:
    return False


@click.command()
@click.argument("--filter", "-f", default=".*")
def main(filter: str):
    for mac_address in get_mac_addresses(filter):
        if not is_local(mac_address.ip):
            print(mac_address)

if __name__ == "__main__":
    main()
