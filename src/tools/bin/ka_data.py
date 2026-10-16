import json
import logging
import os
import subprocess
from collections import defaultdict
from glob import glob
from socket import gethostname

import attr
import click
try:
    from tools.libs.vip_utils import decode_first_line, KaData
except ImportError:
    from vip_utils import decode_first_line, KaData


@attr.s
class Host(object):
    """
    Class to represent an host, wits its reachability status.
    Provides the `run` method to run a remote command
    """
    name: str = attr.ib()
    status_cache = defaultdict(dict)  # {host: {service: True/False}}

    def __attrs_post_init__(self):
        self._is_reachable = None
        self.log = logging.getLogger(__name__)
        self._ssh_options = ["-o", "StrictHostKeyChecking false", "-o", "ConnectTimeout 5", "-o", "BatchMode yes", "-q"]
        self._ssh = ["ssh"] + self._ssh_options + [self.name]
        self._scp = ["scp", "-p"] + self._ssh_options

    @property
    def is_reachable(self) -> bool:
        if self._is_reachable is None:
            try:
                self._is_reachable = self.status_cache[self.name]["ping"]
            except KeyError:
                self._is_reachable = False
                try:
                    subprocess.check_output(
                        ["ping", "-c", "3", "-W", "1", self.name],
                        universal_newlines=True,
                        stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    self._is_reachable = True
                except Exception as e:
                    self.log.debug(f"Problem with {self}: {e}.\n{e.output}")
                self.status_cache[self.name]["ping"] = self._is_reachable
        return self._is_reachable

    def copy(self, srcfiles: list, dest: str):
        if self.is_reachable:
            return subprocess.Popen(
                self._scp + srcfiles + [f"{self.name}:{dest}"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ).wait()
        else:
            return f"{self.name} unreachable"

    def run(self, cmd, *args, **kwargs):
        if self.is_reachable:
            result = subprocess.Popen(
                self._ssh + cmd, universal_newlines=True, stdin=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                *args, **kwargs
            )
            result.wait()
            return result.stdout
        else:
            return f"{self.name} unreachable"


def update_if_not_me(hosts: set, hosts_to_add) -> list:
    _myhn = gethostname().split('.')[0].lower()
    for host in hosts_to_add:
        if _myhn != host.lower():
            hosts.add(host)
    return hosts


def copy_and_run(hostname: str, service: str):
    if (host := Host(hostname)).is_reachable:
        import_file = os.path.join(os.path.dirname(__file__), "..", "libs", "vip_utils.py")
        host.copy([__file__, import_file], "/tmp/")
        click.echo(host.run(["/mnt/opt/nicola/tools/bin/python", "/tmp/ka_data.py", "-s", service]))


@click.command()
@click.argument("filename", default="/tmp/keepalived.data")
@click.option("--service-name", "-s", default="jellyfin")
@click.option("--all-hosts", "-a", default=False, is_flag=True)
def cli(filename: str, service_name: str, all_hosts: bool):
    subprocess.Popen(["killall", "-USR1", "keepalived"])
    ka_data = KaData(filename)
    click.echo(f" * {gethostname()} *")
    for s in ka_data.services.values():
        click.echo(s)
    # click.echo(json.dumps(ka_data.dump_config(service_name), indent=2))
    # click.echo(f"Also available: {', '.join(ka_data.config.keys())}")
    if all_hosts:
        hosts = set()
        for fname in glob("/etc/keepalived/keepalived.d/*.conf"):
            sdict = decode_first_line(fname)
            update_if_not_me(hosts, sdict["vrrp"])
        for host in hosts:
            copy_and_run(host, service_name)


if __name__ == "__main__":
    cli()
