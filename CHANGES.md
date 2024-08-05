## v0.1.2
* add eyed3 dependency (for id3-checker)
## v0.1.1
* minimum Python version is 3.8 (due to `:=` usage)
* fix `logging_utils.py` to use LOG_FORMAT only for stderr, and to limit stderr to DEBUG and stdout to INFO and more
## v0.0.9
* add CloudFlare tools
* add service-map
* improve arp-map
* LoggingArgumentParser fallback to ArgParse `prog_name` for `app_name`
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
