import json
import os
import re
import subprocess
import sys
from collections import defaultdict

from tools.libs.parse_args import LoggingArgumentParser
from tools.libs.stools_defaults import host_if_not_me

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


class ServiceCatalog(object):
    def __init__(self, ka_dir: str):
        self.services = {'keepalived': []}
        self.hosts = defaultdict(list)
        for dirpath, dirnames, filenames in os.walk(ka_dir):
            for filename in filenames:
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
                    self.hosts[host].append(service_name)
                    if 'keepalived' not in self.hosts[host]:
                        self.hosts[host].append('keepalived')

    def file_differs(self, filename, hosts: list) -> bool:
        # re.sub(r'\.?(canne|)$', '.canne', host)
        if 'raspy2' in hosts:
            return True
        return False

    def config_differs(self, service_name, hosts: list = None) -> bool:
        if hosts is None:
            hosts = self.services[service_name]
        try:
            service_config = SERVICE_CONFIGS[service_name]
            if os.path.isdir(service_config):
                return any([
                    self.file_differs(os.path.join(dirpath, filename), hosts)
                    for dirpath, dirnames, filenames in os.walk(service_config)
                    for filename in filenames
                ])
            elif os.path.isfile(service_config):
                return self.file_differs(service_config, hosts)
        except Exception:
            return False


class ServiceConfig(dict):
    def __init__(self, host):
        self.host = host

    def __get__(self, key):
        try:
            return super.__get__(key)
        except Exception:
            self[key] = self._retrieve_config(self.host, key)

    def _retrieve_config(self, filename):
        cache_file = os.path.join(CACHE_DIR, self.host)
        cache_data = None
        try:
            with open(cache_file, 'r') as cache_file:
                cache_data = json.load(cache_file)[filename]
        except Exception as e:
            self.log.debug(f"Cache file {cache_file} does't contain useful data ({e})")
        if cache_data is None:
            cache_data = remote_command(self.host, ['cat', filename])
        return cache_data


def remote_command(host: str, cmd: list):
    return subprocess.check_output(['ssh', host] + cmd).decode('utf-8')


def main(argv: list = sys.argv[1:]):
    cfg = parse_args(argv)
    catalog = ServiceCatalog(cfg.ka_dir)
    if cfg.hosts:
        print(json.dumps(catalog.hosts, indent=2))
    else:
        print(json.dumps(catalog.services, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
