## Nicola's tools
A set of tools to help the management of the home network.  
Currently I have the current services at home:
* Keepalived
* DNS (keepalived)
* OpenVPN (keepalived)
* SMTP relay (keepalived)
* MySQL (keepalived) - mainly for Kodi
* XyMon (keepalived)
* Flask (keepalived)
* Web server (keepalived)
* Tool to configure allowlisted applications (i.e. Minecraft, Firefox, etc)

## sservice
This is meant to start/stop a service managed by Keepalived, by getting the latest config from git and backing up the current config before overwriting.  
It (will) support primary/secondary handling

## minecraft_ctl
This allows to disable or enable running Minecraft (by changing permissions, closing the firewall and killing processes).  
Currently supports (Mac only):
* Minecraft
* Firefox
* Tor Browser
* Diablo III
* Docker
