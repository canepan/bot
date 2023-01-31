import json
import subprocess
import typing
from collections import defaultdict

import click

KNOWN_HOSTS = ['raspy2', 'raspy3', 'phoenix', 'raspym2', 'plone-01']


class ArpMapRecord(object):
    def __init__(self, line: str = None, filter_interface: str = None, known_hosts_styler: callable = None):
        self.filter_interface = filter_interface
        self.fqdn, ip, _, self.mac, remainder = line.split(maxsplit=4)
        self.ip = ip[1:-1]
        self.interface = remainder.split()[-1]
        self.name = self.fqdn if self.fqdn != "?" else self.ip
        self.known_hosts_styler = known_hosts_styler if known_hosts_styler is not None else lambda x: click.style(x, 'green')

    def is_valid(self) -> bool:
        return (self.filter_interface is None or self.interface == self.filter_interface) and 'incomplete' not in self.mac

    def __repr__(self):
        if self.fqdn.split('.')[0].lower() in KNOWN_HOSTS:
            return self.known_hosts_styler(self.name)
        else:
            return self.name


class ArpMapRecords(object):
    def __init__(self, lines: typing.List[str] = None, **kwargs):
        '''
        :param lines: if provided, it should have the same format of the output from `arp -a` on Linux. If None, `arp` is run
        :param kwargs: the remaining parameters are passed to `ArpMapRecord` as-is
        '''
        self._lines = lines
        self.kwargs = kwargs

    @property
    def lines(self) -> typing.List[str]:
        if self._lines is None:
            cmd_result = subprocess.run(['/usr/sbin/arp', '-a'], capture_output=True, text=1)
            self._lines = cmd_result.stdout.splitlines()
        return self._lines

    def __iter__(self) -> typing.Iterable[ArpMapRecord]:
        for line in self.lines:
            record = ArpMapRecord(line, **self.kwargs)
            if record.is_valid():
                yield record


@click.command()
@click.option('-i', '--interface', default=None, help='Only check specified interface')
def main(interface):
    services = defaultdict(list)
    for arp_record in ArpMapRecords(filter_interface=interface):
        if arp_record.fqdn.split('.')[0].lower() in KNOWN_HOSTS:
            services[arp_record.mac].insert(0, arp_record)
        else:
            services[arp_record.mac].append(arp_record)
    for mac, record in services.items():
        click.echo(f'{mac}: {", ".join(map(str, record))}{"" if interface else f" ({record[0].interface})"}')


if __name__ == '__main__':
    main()  # pragma: no cover
