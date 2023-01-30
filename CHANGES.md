## v0.0.8
* use [Click](https://click.palletsprojects.com)
* add `mv.sh` (to be used on synology devices)
* add arp-map (to aggregate hostnames-IP by MAC address from the output of `arp`)
* add `openvpn_log.py` (to filter logs produced by OpenVPN)
* imporve unit tests
## v0.0.7
Import `file` to show MKV info, with fallback to /usr/bin/file (osx).  
Add `service_map` (wip), to show services allocation (from keepalived) in the network.
## v0.0.6
Add GitHub config (`.github/workflows/python-package.yml`).  
Add drawio for home services.  
Import `ipadd`, `backup_kdbx.sh`, `all.py`.  
Add `minecraft_temp.py`, macs.txt (list of mac addresses associations).  
Bugfixes and improvements
## v0.0.5
Add support to configure a remote firewall (currently hardcoded)
