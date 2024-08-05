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

## minecraft_ctl
Script to disable or enable running Minecraft (by changing permissions, closing the firewall and killing processes).  
Currently supports (Mac only):
* Minecraft
* Firefox
* Tor Browser
* Diablo III
* Docker

## service-map
* show running, active services
* reads KeepAlived config (basic)
* uses ssh for remote nodes
* click for colors
* highlight primary/misplaced primary ("usurper")

## sservice
Script meant to start/stop a service managed by Keepalived, by getting the latest config from git and backing up the current config before overwriting.  
It (will) support primary/secondary handling
