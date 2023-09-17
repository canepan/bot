#!/usr/bin/env python3
import json
import logging
import os
import re
import typing
from collections import defaultdict
from glob import glob
from subprocess import check_output, CalledProcessError, STDOUT

import attr
import click

from tools.libs.net_utils import ip_if_not_local

KA_DIR = "/etc/keepalived/keepalived.d"
status_cache = defaultdict(dict)  # {host: {service: True/False}}


def remote_command(host: str, cmd: list) -> str:
    if host:
        run_cmd = ['ssh', host, " ".join(cmd)]
    else:
        run_cmd = ['bash', "-c", " ".join(cmd)]
    return check_output(run_cmd, universal_newlines=True, stderr=STDOUT)


def active(name: str) -> str:
    return f"+{name}"


def is_active(name: str) -> bool:
    return name.startswith("+")


def running(name: str) -> str:
    return name


def is_running(name: str) -> bool:
    return not (failed(name) or active(name))


def failed(name: str) -> str:
    return f"*{name}"


def is_failed(name: str) -> bool:
    return name.startswith("*")


@attr.s(hash=True)
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
                if service.is_active_on(self):
                    result.append(active(service.name))
                elif service.is_running_on(self):
                    result.append(running(service.name))
                else:
                    result.append(failed(service.name))
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


@attr.s
class ServiceStatus(object):
    available: bool = attr.ib(default=None)
    """ Service is running """
    expected: bool = attr.ib(default=None)
    """ Service should be running """
    active: bool = attr.ib(default=None)
    """ Service is the one accessed """


class Service(object):
    def __init__(self, filename: str):
        if os.path.exists(filename):
            self._filename = filename
            self._name = None
        else:
            self._name = filename
            self._filename = os.path.join(KA_DIR, f"{filename}.conf")
        self._check_script = None
        # self._config_name = None
        self._service_dict = None
        self._hosts = None
        self._status = defaultdict(ServiceStatus)
        self.log = logging.getLogger(__name__)

    @property
    def check_script(self):
        if self._check_script is None:
            self._service_dict = self.parse_config()
        return self._check_script

    """
    @property
    def config_name(self):
        if self._config_name is None:
            self._service_dict = self.parse_config()
        return self._config_name
    """

    @property
    def filename(self):
        return self._filename

    @property
    def hosts(self):
        if self._hosts is None:
            self._hosts = self.service_dict.get('vrrp', [])
        return self._hosts

    @property
    def name(self):
        if self._name is None:
            # TODO: replace with vrrp service name from conf
            # self._name = re.sub(r'\.conf$', '', os.path.basename(self.filename))
            self._service_dict = self.parse_config()
        return self._name

    @property
    def service_dict(self):
        if self._service_dict is None:
            self._service_dict = self.parse_config()
        return self._service_dict

    def is_active_on(self, host: Host) -> bool:
        if self._status[host].active is None:
            try:
                self._status[host].active = status_cache[host.name][f"+{self.name}"]
                self.log.debug(f"Returned cache for {host.name}/+{self.name}")
            except KeyError:
                try:
                    # state = remote_command(ip_if_not_local(host.name), [f"awk -F ' - ' '{{print $2}}' '/tmp/{self.name}.state'"])
                    state = remote_command(ip_if_not_local(host.name), [f"cat '/tmp/{self.name}.state'"]).split("-")[1].strip()
                    self._status[host].active = state == "MASTER"
                except CalledProcessError as e:
                    self.log.debug(f"{e}\n{e.stdout}")
                    self._status[host].active = False
                except Exception as e:
                    self.log.debug(f"{e}")
                    self._status[host].active = False
                status_cache[host.name][f"+{self.name}"] = self._status[host].active
        return self._status[host].active

    def is_running_on(self, host: Host) -> bool:
        if self._status[host].available is None:
            try:
                self._status[host].available = status_cache[host.name][self.name]
                self.log.debug(f"Returned cache for {host.name}/{self.name}")
            except KeyError:
                try:
                    remote_command(ip_if_not_local(host.name), [self.check_script])  # [f"/etc/keepalived/bin/check_{self.name}.sh"])
                    self._status[host].available = True
                except CalledProcessError as e:
                    self.log.debug(f"{e}\n{e.stdout}")
                    self._status[host].available = False
                except Exception as e:
                    self.log.debug(f"{e}")
                    self._status[host].available = False
                status_cache[host.name][self.name] = self._status[host].available
        return self._status[host].available

    def parse_config(self) -> dict:
        with open(self.filename, 'r') as f:
            self._name = re.sub(r'\.conf$', '', os.path.basename(self.filename))
            self._check_script = "/etc/keepalived/bin/check_{self._name}.sh"
            try:
                first_line = f.readline()
                for line in f:
                    if line.strip().startswith("script "):
                        self._check_sript = line.split()[1].strip('"')
                    elif line.strip().startswith("vrrp_instance "):
                        self._name = line.split()[1].strip('"')
                return json.loads(first_line.lstrip('#').strip())
            except json.decoder.JSONDecodeError as e:
                raise DecodeFirstLineException(f'Error while decoding {filename} ("{first_line}")') from e

    def should_run_on(self, host: Host) -> bool:
        if self._status[host].expected is None:
            self._status[host].expected = host.name in self.hosts
        return self._status[host].expected

    def __repr__(self):
        repr_hosts = [f"{i * '%'}{h}" for i, h in enumerate(self.hosts)]
        return f"{self.name} ({self.filename}): {', '.join(repr_hosts)}"


def add_color(text: str) -> str:
    if text.startswith("*"):
        return click.style(text, "red", bold=True)
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
            if is_active(service):
                services_dict[service[1:]].append(active(host))
            elif is_failed(service):
                services_dict[service[1:]].append(failed(host))
            else:
                services_dict[service].append(running(host))
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
