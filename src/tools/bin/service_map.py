import json
import os
import re
import sys
from collections import defaultdict

from tools.libs.parse_args import LoggingArgumentParser

SERVICE_CONFIGS = {
    'dns': '/etc/bind',
    'keepalived': '/etc/keepalived',
    'sflask': '/etc/flask.conf',
    'smtp': '/etc/postfix.conf',
    'wifi': '/etc/hostapd.conf',
}


def parse_args(argv: list):
    p = LoggingArgumentParser()
    p.add_argument('--ka-dir', '-k', required=True)
    g = p.add_mutually_exclusive_group()
    g.add_argument('--services', '-S', action='store_true')
    g.add_argument('--hosts', '-H', action='store_true')
    return p.parse_args(argv)


def decode_first_line(filename: str) -> dict:
    with open(filename, 'r') as f:
        return json.loads(next(f).lstrip('#').strip())


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
