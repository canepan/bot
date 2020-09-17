#!/bin/bash
_oui_file="/tmp/oui.txt"
_macs="`arp -na`"
curl -sS "http://standards-oui.ieee.org/oui.txt" -o "${_oui_file}"

for i in `echo "${_macs}" | grep -v -e docker -e incomplete | awk '{print $4}'|sort -u`; do
  grep -qi $i "${HOME}/macs.txt" || echo "${_macs}" | awk '/'$i'/ {gsub(/[()]/, "", $2); print $2, $4}' | while read _ip _mac; do
    echo -n "${_mac} ${_ip} "
    grep -i "`echo ${_mac//:/} | cut -c1-6`" "${_oui_file}" | cut -d')' -f2 | tr -d '\t'
  done
done
