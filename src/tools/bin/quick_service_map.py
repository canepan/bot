#!/mnt/opt/nicola/tools/bin/python
import json
import os
from glob import glob
from subprocess import check_output

from tools.bin.simple_service_map import Service


def get_ip_map():
    ip_map = {}
    cmd = ["all.py", "ip -4 -o ad sh"]
    lines = check_output(cmd, universal_newlines=True).splitlines()
    cmd = ["ip", "-4", "-o", "ad", "sh", "dev", "eth0"]
    local_lines = check_output(cmd, universal_newlines=True).splitlines()
    hostname = os.uname().nodename
    lines.extend(f"{hostname}: {l}" for l in local_lines)

    for line in lines:
        if not line:
            continue
        try:
            hn, _, _, _, ip, _ = line.split(maxsplit=5)
        except ValueError as e:
            print(f"Skipping unparseable line: {line!r} ({e})")
            continue
        ip_map[ip] = hn.rstrip(":")
    return ip_map


def main():
    ip_map = get_ip_map()
    services = [Service(f) for f in glob("/etc/keepalived/keepalived.d/*.conf")]

    for svc in services:
        ip = svc.service_dict["ip"]
        host = ip_map.get(ip, "no active host")
        print(f"{svc.name} ({ip}): {host}")


if __name__ == "__main__":
    main()

"""
#!/bin/bash
all="$(
  all.py 'ip -4 -o ad sh dev eth0'
  ip -4 -o ad sh dev eth0 | sed "s/^/${HOSTNAME}: /g"
  )"
ips="$(echo "${all}" | tr -d ':' | awk '{print $1,$5}')"

echo "${ips}"

exit 0
"""

