#!/usr/bin/env python3
import enum
import json
import logging
import os
import re
import sys
import typing
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from getpass import getuser
from glob import glob
from subprocess import check_output, CalledProcessError, STDOUT

import attr
import click

from tools.libs.net_utils import ip_if_not_local

KA_DIR = "/etc/keepalived/keepalived.d"
KA_CONFIG_DIR = "/etc/keepalived"
KA_CHECKS_DIR = os.path.join(KA_CONFIG_DIR, "bin")
LOCAL_SUBNET_TEMPLATE = "192.168.19.{}/24"

def remote_command(host: str, cmd: list) -> str:
    return _remote_command(host, " ".join(cmd))


@lru_cache(maxsize=50)
def _remote_command(host: str, cmd: str) -> str:
    if host:
        run_cmd = ['ssh', '-o', 'ConnectTimeout=2', host, cmd]
    else:
        run_cmd = ['bash', "-c", cmd]
    return check_output(run_cmd, universal_newlines=True, stderr=STDOUT)


def active(name: str) -> str:
    return f"+{name}"


def is_active(name: str) -> bool:
    return name.startswith("+")


def usurper(name: str) -> str:
    return f"~{name}"


def is_usurper(name: str) -> bool:
    return name.startswith("~")


def running(name: str) -> str:
    return name


def is_running(name: str) -> bool:
    return not (is_failed(name) or active(name))


def failed(name: str) -> str:
    return f"*{name}"


def is_failed(name: str) -> bool:
    return name.startswith("*")


STATES = {f(""): f for f in (active, failed, running, usurper)}


def add_color(text: str) -> str:
    if is_failed(text):
        return click.style(text, "red", bold=True)
    elif is_active(text):
        return click.style(text, "green")
    elif is_usurper(text):
        return click.style(text, "yellow")
    else:
        return text


@attr.s(hash=True)
class Host(object):
    """
    Class to represent an host, wits its reachability status
    """
    name: str = attr.ib()
    status_cache = defaultdict(dict)  # {host: {service: True/False}}

    def __attrs_post_init__(self):
        self._is_reachable = None
        self.log = logging.getLogger(__name__)

    @property
    def is_reachable(self) -> bool:
        if self._is_reachable is None:
            try:
                self._is_reachable = self.status_cache[self.name]["ping"]
            except KeyError:
                self._is_reachable = False
                try:
                    check_output(["ping", "-c", "3", "-W", "1", self.name], universal_newlines=True)
                    remote_command(ip_if_not_local(self.name), ["hostname"])
                    self._is_reachable = True
                except CalledProcessError as e:
                    self.log.debug(f"Problem with {self}: {e}.\n{e.output}")
                except Exception as e:
                    self.log.debug(f"Problem with {self}: {e}.\n{vars(e)}")
                self.status_cache[self.name]["ping"] = self._is_reachable
        return self._is_reachable

    def check_active_services(self, services: list) -> typing.Optional[list]:
        if services is None:
            return None
        result = []
        for service in services:
            self.log.debug(f"Check {service} on {self}")
            if service.should_run_on(self):
                if service.is_active_on(self):
                    result.append(active(service.name) if self.name == service.hosts[0] else usurper(service.name))
                elif service.is_running_on(self):
                    result.append(running(service.name))
                else:
                    result.append(failed(service.name))
            else:
                self.log.debug(f"{service} should not run on {self}")
        return result

    def check_daemon_services(self, services: list) -> list:
        if services is None:
            return None
        result = []
        ka_data = {}
        try:
            ka_statuses = remote_command(
                ip_if_not_local(self.name),
                ["killall", "-USR1", "keepalived", ";", "cat /tmp/keepalived.data"]
            )
        except CalledProcessError as e:
            ka_statuses = ""
        keys = (
            "Virtual Router ID",
            "src_ip",
            "transition",
            "State",
            "Interface",
        )
        click.echo(self)
        for line in ka_statuses.splitlines():
            if "Instance" in line and "=" in line:
                service_name = line.split("=")[1].strip()
                ka_data[service_name] = {}
            for key in keys:
                if key in line and "=" in line:
                    value = line.split("=")[1].strip()
                    if key != "State" or value in ("MASTER", "BACKUP", "FAIL"):
                        ka_data[service_name][key] = value
        click.echo(ka_data)

        legend = set()
        for service in services:
            self.log.debug(f"Check {service} on {self}")
            # if service.should_run_on(self):
            if service.name in ka_data:
                # if ka_data[service.is_active_on(self):
                if ka_data[service.name].get("State") == "MASTER":
                    result.append(active(service.name))
                    legend.add(active("active"))
                elif service.is_running_on(self):
                    result.append(running(service.name))
                    legend.add(running("running"))
                else:
                    result.append(failed(service.name))
                    legend.add(failed("failed"))
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
    """
    Class to represent a VRRP service, with a name and a configuration file
    Fields:
      * filename
      * name
      * hosts
      * service_dict
      * is_running_on(host): if the service is OK on the host
      * is_active_on(host): if the host is the primary
      * should_run_on(host): if the host has highest priority in config
      * _status: dict of {'fqdn': ServiceStatus}
    """
    def __init__(self, filename: str):
        if os.path.exists(filename):
            self._filename = filename
            self._name = None
        else:
            self._name = filename
            self._filename = os.path.join(KA_DIR, f"{filename}.conf")
        self._check_script = None
        self._service_dict = None
        self._hosts = None
        self._status = defaultdict(ServiceStatus)
        self.log = logging.getLogger(__name__)

    @property
    def check_script(self):
        if self._check_script is None:
            self._service_dict = self.parse_config()
        return self._check_script

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
                self._status[host].active = Host.status_cache[host.name][f"+{self.name}"]
                self.log.debug(f"Returned cache for {host.name}/+{self.name}")
            except KeyError:
                try:
                    output = remote_command(ip_if_not_local(host.name), [f"cat '/tmp/{self.name}.state'"])
                    state = output.split("-")[1].strip()
                    self._status[host].active = state == "MASTER"
                except CalledProcessError as e:
                    self.log.debug(f"{e}\n{e.stdout}")
                    self._status[host].active = False
                except Exception as e:
                    self.log.debug(f"{output} - {e}")
                    self._status[host].active = False
                Host.status_cache[host.name][f"+{self.name}"] = self._status[host].active
        return self._status[host].active

    def is_running_on(self, host: Host) -> bool:
        if self._status[host].available is None:
            try:
                self._status[host].available = Host.status_cache[host.name][self.name]
                self.log.debug(f"Returned cache for {host.name}/{self.name}")
            except KeyError:
                try:
                    remote_command(ip_if_not_local(host.name), [self.check_script])
                    self._status[host].available = True
                except CalledProcessError as e:
                    self.log.debug(f"{e}\n{e.stdout}")
                    self._status[host].available = False
                except Exception as e:
                    self.log.debug(f"{e}")
                    self._status[host].available = False
                Host.status_cache[host.name][self.name] = self._status[host].available
        return self._status[host].available

    def parse_config(self) -> dict:
        with open(self.filename, 'r') as f:
            self._name = re.sub(r'\.conf$', '', os.path.basename(self.filename))
            self._check_script = os.path.join(KA_CHECKS_DIR, f"check_{self._name}.sh")
            full_config = {}
            first_line = f.readline()
            try:
                full_config = json.loads(first_line.lstrip('#').strip())
                if "id" in full_config:
                    full_config["ip"] = LOCAL_SUBNET_TEMPLATE.format(full_config["id"])
            except json.decoder.JSONDecodeError as e:
                raise DecodeFirstLineException(f'Error while decoding {self.filename} ("{first_line}")') from e
            next_is_ip = False
            # cl contains the line with "#" comments removed and no leading/trailing spaces
            for line in [cl for l in f if (cl := l.split("#")[0].strip())]:
                if next_is_ip:
                    full_config["ip"] = line.split()[0].strip('"')
                    next_is_ip = False
                elif line.startswith("script "):
                    self._check_script = line.split()[1].strip('"')
                elif line.startswith("vrrp_instance "):
                    self._name = line.split()[1].strip('"')
                elif line.startswith("virtual_router_id "):
                    full_config["id"] = line.split()[1].strip('"')
                    self.log.debug(f"Found id={full_config['id']} from {line}")
                elif line.startswith("virtual_ipaddress "):
                    next_is_ip = True
            return full_config

    def should_run_on(self, host: Host) -> bool:
        if self._status[host].expected is None:
            self._status[host].expected = host.name in self.hosts
        return self._status[host].expected

    def __repr__(self):
        repr_hosts = [f"{i * '%'}{h}" for i, h in enumerate(self.hosts)]
        return f"{self.name} ({self.filename}): {', '.join(repr_hosts)}"


@attr.s
class KeyDisplay(object):
    key: str = attr.ib()

    def __str__(self):
        return click.style(self.key, 'white', bold=True)


class Mood(enum.Enum):
    active = active
    failed = failed
    running = running
    usurper = usurper


@attr.s
class ValueDisplay(object):
    value: str = attr.ib()
    _mood: Mood = attr.ib(init=False, default=None)

    def mood(self):
        return self._mood

    def __str__(self):
        return add_color(self.value)


@attr.s
class ValuesDisplay(object):
    values: typing.Iterable[ValueDisplay] = attr.ib()
    legend: typing.Iterable[ValueDisplay] = attr.ib(default=attr.Factory(list))

    def display(self, value):
        self.legend.add(value.mood(value.mood.name))

    def __str__(self):
        return ", ".join(self.display(v) for v in self.values)


def items_displayer(items: typing.Iterable):
    legend = set()
    for key, values in ((k, v) for (k, v) in sorted(items) if v):
        colored_values = list()
        for value in sorted(values or []):
            colored_values.append(add_color(value))
            if value[0] in STATES:
                legend.add(add_color(f"{value[0]}{STATES[value[0]].__name__}"))
            else:
                legend.add(add_color(STATES[""].__name__))
        yield f"{click.style(key, 'white', bold=True)}: {', '.join(colored_values)}"
    if legend:
        yield f"Legend: {', '.join(sorted(legend))}"


def show_services_by_host(active_services: dict) -> typing.Iterator[str]:
    for line in items_displayer(active_services.items()):
        yield line


def show_services(active_services: dict) -> typing.Iterator[str]:
    services_dict = defaultdict(list)
    legend = set()
    for host, services in active_services.items():
        for service in services or []:
            if is_usurper(service):
                services_dict[service[1:]].append(usurper(host))
                legend.add(usurper("usurper"))
            elif is_active(service):
                services_dict[service[1:]].append(active(host))
                legend.add(active("active"))
            elif is_failed(service):
                services_dict[service[1:]].append(failed(host))
                legend.add(failed("failed"))
            else:
                services_dict[service].append(running(host))
                legend.add(running("running"))
    for line in items_displayer(services_dict.items()):
        yield line


def setup_logging(verbose: typing.Optional[bool]) -> logging.Logger:
    logging.basicConfig(stream=sys.stdout)
    log = logging.getLogger(__name__)
    if (user := f".{getuser()}") == ".root":
        user = ""
    logfile = f"/tmp/{os.path.basename(__file__).split('.')[0]}{user}.log"
    fh = logging.FileHandler(logfile)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    log.addHandler(fh)
    stdout_handler = logging.getLogger().handlers[0]
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.setFormatter(logging.Formatter("%(message)s"))
    if verbose:
        stdout_handler.setLevel(logging.DEBUG)
    elif verbose is False:
        stdout_handler.setLevel(logging.CRITICAL)
    log.setLevel(logging.DEBUG)
    return log


@attr.s
class HostChecker(object):
    hostnames: list = attr.ib()
    query_daemon: bool = attr.ib(default=False)

    def __attrs_post_init__(self):
        self.log = logging.getLogger(__name__)
        self.service_list = {Service(fname) for fname in glob(os.path.join(KA_DIR, "*.conf"))}
        if self.hostnames:
            self.hosts = (Host(hostname) for hostname in self.hostnames)
        else:
            self.hosts = tuple(Host(hostname) for s in self.service_list for hostname in s.hosts)
            self.log.debug(f"Detected hosts: {', '.join(h.name for h in self.hosts)}")

    def check_host(self, host: Host):
        if host.is_reachable:
            self.log.debug(f"{host} is reachable: checking {self.service_list}")
            if self.query_daemon and getuser() == "root":
                return host.name, host.check_daemon_services(self.service_list)
            else:
                return host.name, host.check_active_services(self.service_list)
        else:
            return host.name, None


@click.command()
@click.argument("hostnames", nargs=-1) #, type=set)
@click.option("--by-service", "-s", default=False, is_flag=True)
@click.option("--no-parallel", "-n", default=False, is_flag=True)
@click.option("--query-daemon", "-D", default=False, is_flag=True, help="Root only")
@click.option("--verbose/--quiet", "-v/-q", default=None)
def main(hostnames: set, no_parallel: bool, by_service: bool, query_daemon: bool, verbose: typing.Optional[bool]):
    log = setup_logging(verbose)

    log.debug(f"Starting with {hostnames}")
    try:
        hc = HostChecker(hostnames, query_daemon)
    except Exception as e:
        log.exception(e)
        sys.exit(10)
    if no_parallel:
        active_services = defaultdict(list)
        with click.progressbar(hc.hosts) as hosts:
            for host in hosts:
                if host.is_reachable:
                    log.debug(f"{host} is reachable: checking {hc.service_list}")
                    active_services[host.name].extend(host.check_active_services(hc.service_list))
                else:
                    active_services[host.name] = None
    else:
        log.debug(f"Checking {hc.hosts}")
        with ThreadPoolExecutor(min(50, len(hc.hosts))) as tpool:
            active_services = dict(tpool.map(hc.check_host, hc.hosts))
    if by_service:
        output_lines = show_services(active_services)
    else:
        output_lines = show_services_by_host(active_services)
    log.debug(f"Unreachable: {', '.join(h for h, s in active_services.items() if s is None)}")
    for line in output_lines:
        click.echo(line)


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
import json
import logging
import os
import re
