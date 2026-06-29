## Nicola's tools
A set of tools to help the management of the home network.  
Currently I have these services at home:
* Keepalived
* DNS (keepalived)
* Flask (keepalived)
* JellyFin (docker, keepalived)
* MySQL (keepalived) - mainly for Kodi
* OpenVPN (keepalived)
* PiHole (docker, keepalived)
* SMTP relay (keepalived)
* XyMon (keepalived)
* Web server (keepalived)
* Tool to configure allowlisted applications (i.e. Minecraft, Firefox, etc)

## id3-checker
From a directory, finds songs recursively and shows artist, title and album, alerting on discrepancies

## tags-report
From a directory, finds songs recursively and shows discrepancies or misses in ID3 tags

## minecraft_ctl
Script to disable or enable running Minecraft (by changing permissions, closing the firewall and killing processes).  
Currently supports (Mac only):
* Minecraft
* Firefox
* Tor Browser
* Diablo III
* Docker

## qsm
Quick service map: reads keepalived conf, report services location based on active IPs

## service-map
* show running, active services
* reads KeepAlived config (basic)
* uses ssh for remote nodes
* click for colors
* highlight primary/misplaced primary ("usurper")

## sservice
Script meant to start/stop a service managed by Keepalived, by getting the latest config from git and backing up the current config before overwriting.  
It (will) support primary/secondary handling

## clean_*
Various scripts to cleanup output of commands or logs.  
Use it as a filter in a pipe, like:
```
strace -f -p 666 | clean_strace.sh
```

## vpn-manager
Manage EasyRSA certificates.  
Includes a Xymon reporting parameter, to publish the expiration status to Xymon.  
To allow the creation of graphs for the remaining days, add:
* `,vpncerts=ncv` to TEST2RRD inside `xymonserver.cfg`
* `NCV_vpncerts="*:GAUGE"` to `xymonserver.cfg`
* copy the file `etc/xymon_graphs-vpncerts.cfg` to `/etc/xymon/graphs.d/vpncerts.cfg`

## ssh-cert-manager
Manage SSH user (client) certificates signed by an SSH CA (Python counterpart of `shell/bin/ssh_ca_sign.sh`).
Run with no sub-command for an interactive menu, or use a sub-command:
* `fetch` copy a public key from a remote host (scp) into the ssh-dir
* `sign` create/update (re-sign) a user certificate from `<host>_<user>.pub`
* `distribute` copy the signed certificate back to the remote host's key dir (as `<key>-cert.pub`)
* `list` show issued certificates with principals and expiry
* `check` report expiry status (exit 0/1/2 = ok/warning/critical), optionally to Xymon (`--xymon`)
* `setup-host` configure the local sshd to trust the user CA (root only; writes `/etc/ssh`, does not restart sshd)

Defaults match the shell script: keys in `~/Documents/ssh/`, CA key `~/.ssh/ssh_user_ca`, validity `+52w`.
