import json
import subprocess
from collections import defaultdict

import click

KNOWN_HOSTS = ['raspy2', 'raspy3', 'phoenix', 'raspym2', 'plone-01']


class ArpMapRecords(object):
    def __init__(self, line: str, filter_interface: str):
        self.filter_interface = filter_interface
        self.fqdn, ip, _, self.mac, remainder = line.split(maxsplit=4)
        self.ip = ip[1:-2]
        self.interface = remainder.split()[-1]
        self.name = self.fqdn if self.fqdn != "?" else self.ip

    def is_valid(self) -> bool:
        return (self.filter_interface is None or self.interface == self.filter_interface) and 'incomplete' not in self.mac

    def __repr__(self):
        return f'{self.name} -> {self.mac}'


@click.command()
@click.option('-i', '--interface', default=None, help='Only check specified interface')
def main(interface):
    cmd_result = subprocess.run(['/usr/sbin/arp', '-a'], capture_output=True, text=1)
    services = defaultdict(list)
    for arp_records in [ArpMapRecords(line, filter_interface=interface) for line in cmd_result.stdout.splitlines()]:
        if arp_records.is_valid():
            if arp_records.fqdn.split('.')[0] in KNOWN_HOSTS:
                arp_records.name = click.style(arp_records.name, 'green')
                services[arp_records.mac].insert(0, arp_records)
            else:
                services[arp_records.mac].append(arp_records)
    for mac, record in services.items():
        click.echo(f'{mac}: {", ".join(r.name for r in record)}')


if __name__ == '__main__':
    main()
