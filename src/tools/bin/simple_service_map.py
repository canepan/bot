#!/usr/bin/env python3
import json
from collections import defaultdict
from subprocess import check_output

import attr
import click

from tools.libs.net_utils import ip_if_not_local


def remote_command(host: str, cmd: list) -> str:
    if host:
        cmd = ['ssh', host] + cmd
    return check_output(cmd, universal_newlines=True)


@attr.s
class Host(object):
    name: str = attr.ib()

    def __attrs_post_init__(self):
        self._is_reachable = None

    @property
    def is_reachable(self) -> bool:
        if self._is_reachable is None:
            try:
                check_output(["ping", "-c", "3", "-W", "1", self.name], universal_newlines=True)
                self._is_reachable = True
            except Exception as e:
                click.echo(f"Problem with {self}: {e}")
                self._is_reachable = False
        return self._is_reachable

    def check_active_services(self, services: list) -> list:
        result = []
        for service in services:
            if service.should_run_on(self):
                if service.is_running_on(self):
                    result.append(service.name)
                else:
                    result.append(f"*{service.name}")
        return result


class DecodeFirstLineException(Exception):
    pass


def decode_first_line(filename: str) -> dict:
    with open(filename, 'r') as f:
        try:
            first_line = f.readline()
            return json.loads(first_line.lstrip('#').strip())
        except json.decoder.JSONDecodeError as e:
            raise DecodeFirstLineException(f'Error while decoding {filename} ("{first_line}")') from e


class KAService(object):
    def __init__(self, filename: str):
        self._filename = filename
        self._service_dict = None
        self._service_name = None
        self._hosts = None

    @property
    def filename(self):
        return self._filename

    @property
    def hosts(self):
        if self._hosts is None:
            self._hosts = self.service_dict.get('vrrp', [])
        return self._hosts

    @property
    def service_dict(self):
        if self._service_dict is None:
            self._service_dict = decode_first_line(self.filename)
        return self._service_dict

    @property
    def service_name(self):
        if self._service_name is None:
            # TODO: replace with vrrp service name from conf
            self._service_name = re.sub(r'\.conf$', '', os.path.basename(self.filename))
        return self._service_name

    def __repr__(self):
        repr_hosts = [f"{i * '*'}{h}" for i, h in enumerate(self.hosts)]
        return f"{self.service_name}: {', '.join(repr_hosts)}"


@attr.s
class Service(object):
    name: str = attr.ib()

    def __attrs_post_init__(self):
        self.ka_service = KAService(f"/etc/keepalived/keepalived.d/{self.name}.conf")

    def should_run_on(self, host: Host) -> bool:
        return host.name in self.ka_service.hosts

    def is_running_on(self, host: Host) -> bool:
        try:
            remote_command(ip_if_not_local(host.name), [f"/etc/keepalived/bin/check_{self.name}.sh"])
            return True
        except Exception as e:
            click.echo(e)
            return False


@click.command()
@click.argument("hostnames", nargs=-1) #, type=set)
def main(hostnames: set):
    if hostnames:
        hosts = [Host(hostname) for hostname in hostnames]
    else:
        hosts = [Host(hostname) for hostname in {"phoenix", "raspykey", "raspym2"}]
    service_list = (Service("www"),)
    active_services = defaultdict(list)
    for host in hosts:
        if host.is_reachable:
            click.echo(f"{host} is reachable")
            active_services[host.name].extend(host.check_active_services(service_list))
    print(json.dumps(active_services, indent=2))


if __name__ == "__main__":
    main()
