#!/mnt/opt/nicola/tools/bin/python3
from subprocess import check_output

import click
import netifaces


def arp_table_to_dict(arp_table: list) -> dict:
    arp_dict = {}
    for line in arp_table:
        if "FAILED" not in line:
            fields = line.split()
            arp_dict[fields[0]] = line
            if fields[4] in arp_dict:
                arp_dict[fields[4]].append(fields[0])
            else:
                arp_dict[fields[4]] = [fields[0]]
        # print(line)
    return arp_dict


@click.command()
@click.option("--unsafe", "-u", is_flag=True, help="Must be root")
def main(unsafe: bool):
    ifaddrs = netifaces.ifaddresses("eth0")
    mac_address = ifaddrs[netifaces.AF_LINK][0]['addr']
    arp_table = check_output(["/sbin/ip", "-s", "-s", "neigh", "show"], universal_newlines=True)
    arp_dict = arp_table_to_dict(arp_table.splitlines())
    addresses = []
    # print(json.dumps(arp_dict, indent=2))
    for ipaddr in [i["addr"] for i in ifaddrs[netifaces.AF_INET]]:
        try:
            result = arp_dict[ipaddr]
            addresses.append(ipaddr)
            print(result)
            print(f"  {arp_dict.get(result.split()[4])}")
        except KeyError:
            pass
    if unsafe:
        for ipaddr in addresses:
            print(check_output(["/sbin/ip", "-s", "-s", "neigh", "flush", "to", ipaddr], universal_newlines=True))
    else:
        if addresses:
            print("\nTo clean:\n")
            print("\n".join(f"ip -s -s neigh flush to {ipaddr}" for ipaddr in addresses))


if __name__ =="__main__":
    main()
