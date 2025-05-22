#!/mnt/opt/nicola/tools/bin/python
import os
from subprocess import check_output


def main():
    cmd = ["all.py", "ip -4 -o ad sh dev eth0"]
    all_lines = check_output(cmd, universal_newlines=True).splitlines()
    cmd = ["ip", "-4", "-o", "ad", "sh", "dev", "eth0"]
    all_lines.extend(
        f"{os.uname().nodename} {l}" for l in check_output(cmd, universal_newlines=True).splitlines()
    )
    for line in all_lines:
        hn, _, _, _, ip = line.split(max_split=5)
        print(f"{hn} {ip}")


if __name__ == "__main__":
    main()
    sys.exit(0)


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

