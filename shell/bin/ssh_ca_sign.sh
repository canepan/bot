#!/bin/sh
# Syntax: $0 [hostname [username [domainname]]]
# Source: https://dev.to/gvelrajan/how-to-configure-and-setup-ssh-certificates-for-ssh-authentication-b52
# TL;DR:
#  * ~/.ssh/ssh_user_ca.pub -> <host>:/etc/ssh/
#  * "TrustedUserCAKeys /etc/ssh/ssh_user_ca.pub" -> /etc/ssh/sshd_config (/etc/ssh/sshd_config.d/user_ca.conf)
#  * ${host}_${user_id}-cert.pub -> ${user_id}@<host>:.ssh/

host="${1:-$(hostname)}"
user_id="${2:-${USER}}"
domain="${3:-$(domainname)}"

infile="${HOME}/Documents/ssh/${host}_${user_id}.pub"

if [ ! -f "${infile}" ]; then
  echo "'${infile}' not found"
  exit 1
fi

ssh-keygen -s ~/.ssh/ssh_user_ca -I "${user_id}@${domain}" -n "${user_id}" -V +52w "${infile}"

echo "Generated cert for '${infile}' (${user_id}@${domain})"

