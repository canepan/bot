## v0.1.3
New tools:
* add `ka-status` (`keepalived_status.py`): parse `keepalived.data` and show VRRP state
  and VIP distribution
  * supports both keepalived v1.x and v2.x dump formats (section-aware parser)
  * reverse-resolves node IPs to short hostnames (`--no-resolve` to disable)
  * `--signal` sends SIGUSR1 to keepalived to regenerate the dump before reading
  * `--simple` prints a compact `name (vip): owner (candidate hosts)` line
* add `vpn-manager` (typer-based) to manage an EasyRSA PKI: init-pki, build-ca,
  build-server/build-client, revoke, renew, gen-crl, gen-dh, list, show, export
  (`.ovpn` bundle), and `xymon` to report certificate expiry
* add `xymon-ip-check`: compare the public IPv4 (ifconfig.io) against an external DNS
  lookup and report the result to Xymon
* add `tags-report` (`music_tags_report.py`, evolution of `id3-checker`): report ID3
  discrepancies/missing tags; skips Synology `@eaDir` dirs and silences eyeD3 warnings
* add `retmt` (Perl and Python) to monitor Raspberry Pi temperature
* add `remote_diff.py`; `ssh_ca_sign.sh` (sign SSH user certs); `clean_strace.sh`
* add `rename_media.sh`: normalize TV-episode filenames (handles `...`, multiple
  abbreviations, and 3-letter acronyms), covered by BATS tests

Improvements:
* `qsm`/`simple_service_map`: derive VIPs from `virtual_router_id`/`virtual_ipaddress`,
  show service names, also show other nodes, add a progress bar, fix `is_running` check
* `net_utils`: move `hosts_from_dns`/`HOSTS` here (shared with `all.py`), make dnspython
  optional, fall back to a hardcoded host list when no DNS zone is given
* `xymon` lib: `send_status` accepts a status duration (lifetime) and a per-app logger,
  enabling cert-expiry graphs / 24h validity for `vpn-manager`
* `xymon-speedtest`: fix reading the last log line, add package/script import fallback

Testing & CI:
* add BATS support for shell testing (`test/shell/`) via a dedicated tox `bats` env
* fetch git submodules in GitHub Actions (fixes bats helper `load` failures)
* run tests through tox, selecting the env per Python version with `tox-gh-actions`
* bump GitHub Actions to `checkout@v6` / `setup-python@v6`
* drop Python 3.9, add 3.11 and 3.12 to the test matrix
* add dedicated `lint` (flake8) and `format` (ruff) tox envs

Packaging & docs:
* modernize packaging: replace `setup.py` with `pyproject.toml` (egg/egg_info under `build/`)
* add `eyed3` dependency (for `id3-checker`/`tags-report`)
* document the new tools in `README.md`; add `etc/xymon_graphs-vpncerts.cfg` and Xymon
  graph setup for VPN cert expiry
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
