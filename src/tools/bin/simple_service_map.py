#!/usr/bin/env python3
import json
import logging
import os
import re
import typing
from collections import defaultdict
from glob import glob
from subprocess import check_output, STDOUT

import attr
import click

from tools.libs.net_utils import ip_if_not_local

KA_DIR = "/etc/keepalived/keepalived.d"
status_cache = defaultdict(dict)  # {host: {service: True/False}}


def remote_command(host: str, cmd: list) -> str:
    if host:
        cmd = ['ssh', host] + cmd
    return check_output(cmd, universal_newlines=True, stderr=STDOUT)


@attr.s
class Host(object):
    name: str = attr.ib()

    def __attrs_post_init__(self):
        self._is_reachable = None
        self.log = logging.getLogger(__name__)

    @property
    def is_reachable(self) -> bool:
        if self._is_reachable is None:
            try:
                self._is_reachable = status_cache[self.name]["ping"]
            except KeyError:
                try:
                    check_output(["ping", "-c", "3", "-W", "1", self.name], universal_newlines=True)
                    self._is_reachable = True
                except Exception as e:
                    self.log.debug(f"Problem with {self}: {e}")
                    self._is_reachable = False
                status_cache[self.name]["ping"] = self._is_reachable
        return self._is_reachable

    def check_active_services(self, services: list) -> list:
        result = []
        for service in services:
            self.log.debug(f"Check {service} on {self}")
            if service.should_run_on(self):
                if service.is_running_on(self):
                    result.append(service.name)
                else:
                    result.append(f"*{service.name}")
            else:
                self.log.debug(f"{service} should not run on {self}")
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


class Service(object):
    def __init__(self, filename: str):
        if os.path.exists(filename):
            self._filename = filename
            self._name = None
        else:
            self._name = filename
            self._filename = os.path.join(KA_DIR, f"{filename}.conf")
        self._service_dict = None
        self._hosts = None
        self.log = logging.getLogger(__name__)

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
    def name(self):
        if self._name is None:
            # TODO: replace with vrrp service name from conf
            self._name = re.sub(r'\.conf$', '', os.path.basename(self.filename))
        return self._name

    def should_run_on(self, host: Host) -> bool:
        return host.name in self.hosts

    def is_running_on(self, host: Host) -> bool:
        try:
            result = status_cache[host.name][self.name]
            self.log.debug(f"Returned cache for {host.name}/{self.name}")
        except KeyError:
            try:
                remote_command(ip_if_not_local(host.name), [f"/etc/keepalived/bin/check_{self.name}.sh"])
                result = True
            except Exception as e:
                self.log.debug(e)
                result = False
            status_cache[host.name][self.name] = result
        return result

    def __repr__(self):
        repr_hosts = [f"{i * '*'}{h}" for i, h in enumerate(self.hosts)]
        return f"{self.name}: {', '.join(repr_hosts)}"


def add_color(text: str) -> str:
    if text.startswith("*"):
        return click.style(text, "red")
    elif text.startswith("+"):
        return click.style(text, "green")
    else:
        return text

def show_services_by_host(active_services) -> typing.Iterator[str]:
    for host, services in active_services.items():
        yield f"{click.style(host, 'white', bold=True)}: {', '.join(add_color(service) for service in services)}"


def show_services(active_services) -> typing.Iterator[str]:
    services_dict = defaultdict(list)
    for host, services in active_services.items():
        for service in services:
            if service.startswith("*"):
                services_dict[service[1:]].append(f"*{host}")
            else:
                services_dict[service].append(host)
    for service, hosts in services_dict.items():
        yield f"{click.style(service, 'white', bold=True)}: {', '.join(add_color(host) for host in hosts)}"


def setup_logging(verbose: typing.Optional[bool]) -> logging.Logger:
    logging.basicConfig()
    log = logging.getLogger(__name__)
    fh = logging.FileHandler("/tmp/service_map.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    log.addHandler(fh)
    logging.getLogger().handlers[0].setLevel(logging.INFO)
    if verbose:
        logging.getLogger().handlers[0].setLevel(logging.DEBUG)
    elif verbose is False:
        logging.getLogger().handlers[0].setLevel(logging.CRITICAL)
    log.setLevel(logging.DEBUG)
    return log


@click.command()
@click.argument("hostnames", nargs=-1) #, type=set)
@click.option("--by-service", "-s", default=False, is_flag=True)
@click.option("--verbose/--quiet", "-v/-q", default=None)
def main(hostnames: set, by_service:bool, verbose: typing.Optional[bool]):
    log = setup_logging(verbose)

    service_list = {Service(fname) for fname in glob(os.path.join(KA_DIR, "*.conf"))}
    if hostnames:
        hosts = [Host(hostname) for hostname in hostnames]
    else:
        hosts = []
        for s in service_list:
            for hostname in s.hosts:
                if Host(hostname) not in hosts:
                    hosts.append(Host(hostname))
        log.debug(f"Detected hosts: {', '.join(h.name for h in hosts)}")

    active_services = defaultdict(list)
    for host in hosts:
        if host.is_reachable:
            log.debug(f"{host} is reachable: checking {service_list}")
            active_services[host.name].extend(host.check_active_services(service_list))
    if by_service:
        output_lines = show_services(active_services)
    else:
        output_lines = show_services_by_host(active_services)
    for line in output_lines:
        click.echo(line)


if __name__ == "__main__":
    main()
