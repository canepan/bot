import json
import logging
import subprocess
import socket
from collections import defaultdict

import attr


def is_proxy() -> bool:
    _proxy_ip = socket.gethostbyname('proxy')
    out = subprocess.check_output(['/sbin/ip', '-o', 'addr']).decode('utf-8')
    for line in out.splitlines():
        if _proxy_ip in line:
            return True
    return False


class DecodeFirstLineException(Exception):
    pass


def decode_first_line(filename: str) -> dict:
    with open(filename, 'r') as f:
        try:
            first_line = f.readline()
            return json.loads(first_line.lstrip('#').strip())
        except json.decoder.JSONDecodeError as e:
            raise DecodeFirstLineException(f'Error while decoding {filename} ("{first_line}")') from e


@attr.define
class KaService(object):
    name: str
    router_id: int
    priority: int
    effective_priority: int
    last_transition: str

    def is_running(self):
        return self.priority == self.effective_priority

    @classmethod
    def from_config(cls, dict_config: dict):
        return cls(
            name=dict_config["name"],
            router_id=int(dict_config["Virtual Router ID"]),
            priority=int(dict_config["Priority"]),
            effective_priority=int(dict_config["Effective priority"]),
            last_transition=dict_config["Last transition"],
        )


@attr.s
class KaData(object):
    filename: str = attr.ib()

    def __attrs_post_init__(self):
        self.log = logging.getLogger(__name__)
        self._config = None
        self._services = None

    def dump_config(self, service_name: str) -> dict:
        return self.config[service_name]

    @property
    def services(self) -> str:
        if self._services is None:
            self.config
        return self._services

    @property
    def config(self) -> str:
        if self._config is None:
            self._services = dict()
            self._config = defaultdict(dict)
            try:
                line = ""
                with open(self.filename, "r") as f:
                    item_config = {}
                    name = None
                    for line in f:
                        if line.startswith(" VRRP Instance"):
                             if item_config:
                                 self._services[name] = KaService.from_config(item_config)
                                 item_config = {}
                             name = line.strip().split(" = ")[1]
                             item_config["name"] = name
                        elif line.startswith("---"):
                             name = f'* {line.replace("------< ", "").replace(" >------", "").strip()}'
                             item_config = self._config[name]
                        else:
                            line = line.strip()
                            if " = " in line:
                                key, value = line.split(" = ")
                            else:
                                key, value = line.rsplit(" ", 1) if " " in line else ("", line)
                            item_config[key] = value
                            self._config[name][key] = value
            except Exception as e:
                self.log.exception(f"Error while opening {self.filename} or decoding line '{line.strip()}': {e}")
        return self._config
