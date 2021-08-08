#!/Users/lucia/Documents/Nicola/venv/daemon/bin/python
import argparse
import os
import sys
import subprocess
import time

import daemon

FLAG_FILE = '/var/run/minecraft_allowed'


def create_flag_file():
    with open(FLAG_FILE, 'w') as f:
        f.write('Enabled')


def remove_flag_file():
    os.remove(FLAG_FILE)


def wait_to_disable(sleep_time: int):
    time.sleep(sleep_time * 60)
    remove_flag_file()


def parse_args(argv: list) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('how_long', type=int, help='Number of minutes to allow')
    return parser.parse_args(argv)


def main(argv: list = sys.argv[1:]):
    cfg = parse_args(argv)
    create_flag_file()
    fw_key = os.path.join(os.environ['HOME'], '.ssh', 'mt_remote')
    fw_cmd = f'/ip firewall address-list add list=KidsTemporaryAllow address=192.168.19.137 timeout={cfg.how_long}m'
    output = subprocess.check_output(
        ['ssh', '-i', fw_key, 'manage_internet@mt', fw_cmd], stderr=subprocess.STDOUT
    ).decode('utf-8')
    with daemon.DaemonContext():
        wait_to_disable(cfg.how_long)


if __name__ == '__main__':
    sys.exit(main())
