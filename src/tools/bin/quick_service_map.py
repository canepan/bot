#!/mnt/opt/nicola/tools/bin/python
import json
import os
from glob import glob
from subprocess import check_output

from tools.bin.simple_service_map import Service


def main():
    cmd = ["all.py", "ip -4 -o ad sh dev eth0"]
    all_lines = check_output(cmd, universal_newlines=True).splitlines()
    cmd = ["ip", "-4", "-o", "ad", "sh", "dev", "eth0"]
    all_lines.extend(
        f"{os.uname().nodename}: {l}" for l in check_output(cmd, universal_newlines=True).splitlines()
    )
    ip_map = {}
    for line in all_lines:
        hn, _, _, _, ip, _ = line.split(maxsplit=5)
        ip_map[ip] = {"hostname": hn.rstrip(":")}
    configs = {}
    for conf_file in glob("/etc/keepalived/keepalived.d/*.conf"):
        service = Service(conf_file)
        configs[conf_file] = Service(conf_file)
    for ip, data in ip_map.items():
        for conf_file, config_content in configs.items():
            if ip == config_content.service_dict["ip"]:
                data["name"] = configs[conf_file].name
                data["config"] = configs[conf_file].service_dict
                print(f"{data['name']} ({ip}): {data['hostname']}")


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

