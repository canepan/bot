#!/bin/bash
squid_conf="/etc/squid/squid.d/nicola.acl"
case `basename $0 .sh` in
  allow_internet)
    sed -i 's/^\(http_access deny NIGHT all\)/# \1/' "${squid_conf}"
    rule_changed=1
    ;;
  deny_internet)
    sed -i 's/^# *\(http_access deny NIGHT all\)/\1/' "${squid_conf}"
    rule_changed=1
    ;;
esac
[[ -n $rule_changed ]] && /etc/init.d/squid reload
