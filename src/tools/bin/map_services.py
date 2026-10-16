#!/mnt/opt/nicola/tools/bin/python3
import attr
import json
import sys
from enum import Enum

from tools.libs.stools_defaults import host_if_not_me, parse_args


class KAState(Enum):
    BACKUP = 1
    MASTER = 2
    FAULT = 3


@attr.s
class KeepalivedService(object):
    name: str = attr.ib()
    configured_state: KAState = attr.ib()
    runtime_state: KAState = attr.ib(default=None)

    @classmethod
    def from_config(cls, config_dict: dict) -> 'KeepalivedService':
        return cls(config_dict['name'], config_dict['state'])


def main(argv: list = sys.argv[1:]):
    # kaconfig = json.
    print(KeepalivedService.from_config(kaconfig))


if __name__ == '__main__':
    sys.exit(main())
