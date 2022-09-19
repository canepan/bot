import json
import logging
import os
import re
import subprocess
import sys
from collections import defaultdict

import attr

from tools.libs.parse_args import LoggingArgumentParser
from tools.libs.net_utils import ip_if_not_local

SERVICE_CONFIGS = {
    'dns': '/etc/bind',
    'keepalived': '/etc/keepalived',
    'sflask': '/etc/flask.conf',
    'smtp': '/etc/postfix.conf',
    'wifi': '/etc/hostapd.conf',
}
CACHE_DIR = os.path.join(os.environ['HOME'], '.service_map')


def parse_args(argv: list):
    p = LoggingArgumentParser()
    p.add_argument('--ka-dir', '-k', required=True)
    g = p.add_mutually_exclusive_group()
    g.add_argument('--services', '-S', action='store_true')
    g.add_argument('--hosts', '-H', action='store_true')
    return p.parse_args(argv)


def decode_first_line(filename: str) -> dict:
    with open(filename, 'r') as f:
        try:
            return json.loads(f.readline().lstrip('#').strip())
        except json.decoder.JSONDecodeError as e:
            print(f'Error while decoding {filename} ({f.read()}): {e}')
            raise


def error(text: str) -> str:
    return f'Error: {text}'


@attr.s(repr=False, hash=True)
class ServiceConfig(dict):
    '''
    This is a dict with a `host` property to identify which host contains the configuration in the dict.
    The keys of the dict are filenames, while the values are the contents of the files.
    A cache is maintained in `${HOME}/.service_map/<hostname>.json`
    '''
    host: str = attr.ib()
    service_name: str = attr.ib()
    log: logging.Logger = attr.ib(default=logging.getLogger(__name__))

    def __getitem__(self, key):
        try:
            return super().__getitem__(key)
        except Exception:
            self[key] = self._retrieve_config(key)
        return super().__getitem__(key)

    def _retrieve_config(self, filename):
        if not os.path.isdir(CACHE_DIR):
            os.mkdir(CACHE_DIR)
        cache_file_name = os.path.join(CACHE_DIR, f'{self.host}.json')
        cache_data = None
        all_data = {}
        if ip_if_not_local(self.host):
            try:
                with open(cache_file_name, 'r') as cache_file:
                    all_data = json.load(cache_file)
                    cache_data = all_data[filename]
            except Exception as e:
                self.log.debug(f"Cache file {cache_file_name} does't contain useful data ({e})")
        else:
             self.host = None
        if cache_data is None:
            cache_data = remote_command(self.host, ['cat', filename])
            all_data[filename] = cache_data
            with open(cache_file_name, 'w') as cache_file:
                json.dump(all_data, cache_file)
        return cache_data

    def __repr__(self):
        print(f'repr {self.host}:{self.service_name}')
        if self.service_name in SERVICE_CONFIGS:
            return self[SERVICE_CONFIGS[self.service_name]]
        return super().__repr__()

    def __str__(self):
        print(f'str {self.host}:{self.service_name}')
        return super().__str__()


class ServiceCatalog(object):
    def __init__(self, ka_dir: str, log: logging.Logger):
        self.log = log
        # cache for the `ServiceConfig`s
        self.service_configs = dict()
        # {service: [host1, host2, ...]}
        self.services = {'keepalived': []}
        # {host: [service1, service2, ...]}
        self.hosts = defaultdict(set)
        for dirpath, dirnames, filenames in os.walk(ka_dir):
            for filename in filenames:
                # TODO: replace with vrrp service name from conf
                service_name = re.sub(r'\.conf$', '', filename)
                service_dict = decode_first_line(os.path.join(dirpath, filename))
                self.services[service_name] = service_dict['vrrp']
                for i, host in enumerate(service_dict['vrrp'][1:]):
                    service_dict['vrrp'][i + 1] = f"{i * '*'}{service_dict['vrrp'][i + 1]}"
                    if self.config_differs(service_name, [service_dict['vrrp'][0], host]):
                        service_dict['vrrp'][i + 1] = error(service_dict['vrrp'][i + 1])
                if self.config_differs(service_name):
                    for i in range(len(service_dict['vrrp'])):
                        pass
                self.services['keepalived'].extend(
                    [h for h in service_dict['vrrp'] if h not in self.services['keepalived']]
                )
                for host in service_dict['vrrp']:
                    self.hosts[host].add(ServiceConfig(host, service_name))
                    self.hosts[host].add(ServiceConfig(host, 'keepalived'))

    def file_differs(self, filename, hosts: list, service_name: str) -> bool:
        # re.sub(r'\.?(canne|)$', '.canne', host)
        for host in hosts:
            if host not in self.service_configs:
                self.log.debug(f'Adding {host} to cache')
                self.service_configs[host] = ServiceConfig(host, service_name)
        for host in hosts[1:]:
            if self.service_configs[host][filename] != self.service_configs[hosts[0]][filename]:
                return True
        return False

    def config_differs(self, service_name, hosts: list = None) -> bool:
        if hosts is None:
            hosts = self.services[service_name]
        try:
            service_config = SERVICE_CONFIGS[service_name]
            if os.path.isdir(service_config):
                return any([
                    self.file_differs(os.path.join(dirpath, filename), hosts, service_name)
                    for dirpath, dirnames, filenames in os.walk(service_config)
                    for filename in filenames
                ])
            elif os.path.isfile(service_config):
                return self.file_differs(service_config, hosts)
        except Exception as e:
            self.log.debug(f'Exception while comparing configs: {e}')
            return False


def remote_command(host: str, cmd: list):
    if host:
        cmd = ['ssh', host] + cmd
    return subprocess.check_output(cmd).decode('utf-8')


def main(argv: list = sys.argv[1:]):
    cfg = parse_args(argv)
    catalog = ServiceCatalog(cfg.ka_dir, cfg.log)
    if cfg.hosts:
        cfg.log.info(json.dumps(catalog.hosts, indent=2, default=str))
    else:
        cfg.log.info(json.dumps(catalog.services, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
