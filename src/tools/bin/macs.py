import json
from subprocess import check_output

import attr
import click


def read_lines(infile: str):
    with open(infile, "r") as f:
        result = [line.strip() for line in f]
    return result


@attr.s
class FileAsDict(object):
    conf_file: str = attr.ib()

    def __attrs_post_init__(self):
        self._file_content = None

    @property
    def file_content(self):
        if self._file_content is None:
            self._file_content = read_lines(self.conf_file)
        return self._file_content

    def __getitem__(self, key: str) -> str:
        for line in self.file_content:
            if key in line:
                return line


def arp_transform(arp_host):
    if arp_host[5] == "STALE":
        return f"({arp_host[0]})"
    return arp_host[0]


@attr.s()
class ArpHost(object):
    arp: str = attr.ib(converter=arp_transform)
    config: str = attr.ib()


@click.command
@click.argument("macs_file")
def main(macs_file: str):
    """
    Example: 
    192.168.19.116 dev eth0 lladdr 00:11:32:29:65:2e REACHABLE
    192.168.19.146 dev eth0 lladdr 54:af:97:60:f4:ff STALE
    """
    hosts = dict()
    config = FileAsDict(macs_file)
    for line in check_output(["ip", "neigh"], universal_newlines=True).splitlines():
        col = line.split() if "lladdr" in line else []
        if len(col) >= 5 and config[col[4]]:
            hosts[col[4]] = ArpHost(arp=col, config=config[col[4]])
    for key, host in hosts.items():
        click.echo(f"{key}: {host.arp} / {host.config}")


if __name__ == "__main__":
    main()
