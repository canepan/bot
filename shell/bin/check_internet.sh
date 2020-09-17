#!/bin/bash

check_e2guardian() {
  _url="${1:-https://www.google.com}"
  http_code="`curl -m 3 -x 127.0.0.1:9080 -w '%{http_code}' ${_url} -o /dev/null -s -L`"
  if [ "${http_code}" != "200" -a "${http_code}" != "302" ]; then
    echo "${_url} not accessible via E2Guardian"
    exit 2
  fi
}

check_squid() {
  _url="${1:-https://www.cnn.com}"
  http_code="`curl -m 3 -x 127.0.0.1:3128 -w '%{http_code}' ${_url} -o /dev/null -s -L`"
  if [ "${http_code}" != "200" -a "${http_code}" != "302" ]; then
    echo "${_url} not accessible via Squid"
    exit 4
  fi
}

check_direct() {
  _url="${1:-https://duckduckgo.com}"
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
  http_code="`curl -m 3 -w '%{http_code}' ${_url} -o /dev/null -s -L`"
  if [ "${http_code}" != "200" -a "${http_code}" != "302" ]; then
    echo "${_url} not accessible"
    exit 8
  fi
}

check_ping() {
  _ip="${1:-8.8.8.8}"
  ping -c 2 -w 3 "${_ip}" &> /dev/null
  _errcode=$?
  if [ ${_errcode} -ne 0 ]; then
    echo "${_ip} not reachable"
    exit 16
  fi
}

check_dns() {
  _fqdn="${1:-www.amazon.com}"
  _dns="${2:-8.8.8.8}"
  host -W 3 "${_fqdn}" "${_dns}" | grep -q NXDOMAIN
  if [ $? -eq 0 ]; then
    echo "${_fqdn} not resolvable by ${_dns}"
    exit 32
  fi
  host -W 3 "${_fqdn}" | grep -q NXDOMAIN
  if [ $? -eq 0 ]; then
    echo "${_fqdn} not resolvable"
    exit 32
  fi
}

_err=0
for check in e2guardian squid direct dns ping; do
  check_${check}
  _err=$?
done
#check_e2guardian
#_err=$?
#check_squid
#_err=$(($? + _err))
#check_direct
#_err=$(($? + _err))
#check_dns
#_err=$(($? + _err))
#check_ping
#_err=$(($? + _err))

exit $_err
