#!/bin/bash

_proxy_ip=192.168.19.80

#_basedir="`dirname $0`"
#_basename="`basename $0 .up`"
#_basename="`basename ${_basename} .down`"
#
#[[ -r ${_basedir}/${_basename}.lib ]] && . "${_basedir}/${_basename}.lib"

if [[ -r /etc/openvpn/logs/ovpn.Andrea.vars ]]; then
  . /etc/openvpn/logs/ovpn.Andrea.vars
else
  exit 0
fi

_this_ip="`curl -s -m 2 http://ifconfig.io`"
echo "curl -s -m 2 --interface ${_proxy_ip} http://ifconfig.io"
_other_ip="`curl -s -m 2 --interface ${_proxy_ip} http://ifconfig.io`"

ip ro list table Andrea | grep -q default
route_present=$?

if [[ ${_cmd} == "add" && ( -z ${_other_ip} || ${_other_ip} == ${_this_ip} ) ]]; then
  if [[ $route_present -eq 0 ]]; then
    echo "Restoring normal routing from ${_proxy_ip}"
    ip route del default via ${remote_ip} dev ${dev} table Andrea
  fi
else
  if [[ $route_present -ne 0 ]]; then
    ip route add default via ${remote_ip} dev ${dev} table Andrea
  fi
fi

