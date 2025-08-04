import json
import socket
import subprocess
import typing
from collections import defaultdict

import click
import netifaces

KNOWN_HOSTS = ['raspy2', 'raspy3', 'phoenix', 'raspym2', 'plone-01']


class ArpMapRecord(object):
    seen_names: dict = {}

    def __init__(
        self,
        fqdn: str = None,
        ip: str = None,
        mac: str = None,
        interface: str = None,
        known_hosts_styler: callable = None,
        duplicate_hosts_styler: callable = None,
    ):
        self.fqdn = fqdn
        self.ip = ip
        self.mac = mac
        self.interface = interface
        self.name = self.fqdn if self.fqdn != "?" else self.ip
        self.known_hosts_styler = (
            known_hosts_styler if known_hosts_styler is not None else lambda x: click.style(x, 'green')
        )
        self.duplicate_hosts_styler = (
            duplicate_hosts_styler if duplicate_hosts_styler is not None else lambda x: click.style(x, 'red')
        )
        if self.name in ArpMapRecord.seen_names:
            ArpMapRecord.seen_names[self.name] = self.duplicate_hosts_styler(self.name)
        else:
            ArpMapRecord.seen_names[self.name] = self.name

    @classmethod
    def from_line(cls, line: str = None, known_hosts_styler: callable = None):
        fqdn, ip, _, mac, remainder = line.split(maxsplit=4)
        ip = ip[1:-1]
        interface = remainder.split()[-1]
        name = fqdn if fqdn != "?" else ip
        known_hosts_styler = known_hosts_styler if known_hosts_styler is not None else lambda x: click.style(x, 'green')
        return cls(fqdn=fqdn, ip=ip, mac=mac, interface=interface, known_hosts_styler=known_hosts_styler)

    def is_valid(self) -> bool:
        return 'incomplete' not in self.mac

    def __repr__(self):
        if self.fqdn.split('.')[0].lower() in KNOWN_HOSTS:
            return self.known_hosts_styler(self.name)
        else:
            return ArpMapRecord.seen_names[self.name]


class ArpMapRecords(object):
    def __init__(self, lines: typing.List[str] = None, filter_interface: str = None, **kwargs):
        '''
        :param lines: if provided, it should have the same format of the output from `arp -a` on Linux.
            If None, `arp -a` is run.
        :param filter_interface: if provided, filters the MACs on the specific interface.
        :param kwargs: the remaining parameters are passed to `ArpMapRecord` as-is
        '''
        self._lines = lines
        self.filter_interface = filter_interface
        self.kwargs = kwargs

    @property
    def lines(self) -> typing.List[str]:
        if self._lines is None:
            cmd_result = subprocess.run(['/usr/sbin/arp', '-a'], env={'LANG': ''}, capture_output=True, text=1)
            self._lines = cmd_result.stdout.splitlines()
        return self._lines

    def __iter__(self) -> typing.Iterable[ArpMapRecord]:
        for line in [l for l in self.lines if self.filter_interface is None or l.endswith(self.filter_interface)]:
            record = ArpMapRecord.from_line(line, **self.kwargs)
            if record.is_valid():
                yield record


class LocalMacRecords(object):
    def __init__(self, filter_interface: str = None, **kwargs):
        '''
        :param kwargs: the remaining parameters are passed to `ArpMapRecord` as-is
        '''
        self.filter_interface = filter_interface
        self.kwargs = kwargs
        self._records = None

    @property
    def records(self) -> typing.List[str]:
        if self._records is None:
            self._records = []
            for iface_name in [self.filter_interface] if self.filter_interface else self.list_ifaces():
                ifaddrs = netifaces.ifaddresses(iface_name)
                mac_address = ifaddrs[netifaces.AF_LINK][0]['addr']
                for ip in ifaddrs[netifaces.AF_INET]:
                    fqdn = resolve_ip(ip['addr'])
                    self._records.append(ArpMapRecord(fqdn=fqdn, ip=ip['addr'], mac=mac_address, interface=iface_name))
        return self._records

    def list_ifaces(self) -> list:
        # Only return records with IPv4 addresses
        return [i for i in netifaces.interfaces() if has_ip_and_mac(i)]

    def __iter__(self) -> typing.Iterable[ArpMapRecord]:
        for record in self.records:
            # record = ArpMapRecord(line, filter_interface=self._filter_interface, **self.kwargs)
            if record.is_valid():
                yield record


def add_record_to_list(record: ArpMapRecord, records_list: list) -> None:
    if record.fqdn.split('.')[0].lower() in KNOWN_HOSTS:
        records_list.insert(0, record)
    else:
        records_list.append(record)


def has_ip_and_mac(interface) -> bool:
    ifaddrs = netifaces.ifaddresses(interface)
    return netifaces.AF_INET in ifaddrs and netifaces.AF_LINK in ifaddrs


def resolve_ip(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception as e:
        print(e)
        return '?'


@click.command()
@click.option('-i', '--interface', default=None, help='Only check specified interface')
@click.option('-d', '--mark-duplicates', is_flag=True, default=False, help='Mark duplicate IPs/FQDNs')
def main(interface, mark_duplicates: bool):
    services = defaultdict(list)
    for arp_record in LocalMacRecords(filter_interface=interface):
        add_record_to_list(arp_record, services[arp_record.mac])
    for arp_record in ArpMapRecords(filter_interface=interface):
        add_record_to_list(arp_record, services[arp_record.mac])
    for mac, record in services.items():
        click.echo(f'{mac}: {", ".join(map(str, record))}{"" if interface else f" ({record[0].interface})"}')


if __name__ == '__main__':
    main()  # pragma: no cover
