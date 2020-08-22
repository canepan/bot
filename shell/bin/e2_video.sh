#!/bin/bash
_bin="`dirname ${0}`/config_proxy"
case "$1" in
  enable)
    "${_bin}" -c /etc/squidguard/kids_allow_video.cfg --unsafe
    "${_bin}" -c /etc/e2guardian/kids_allow_video.cfg --unsafe
    [ $? -ne 0 ] && exit 0
    ;;
  disable)
    "${_bin}" -c /etc/squidguard/kids.cfg --unsafe
    "${_bin}" -c /etc/e2guardian/kids.cfg --unsafe
    [ $? -ne 0 ] && exit 0
    ;;
  *)
    echo "$0 enable|disable"
    exit 1
    ;;
esac
sudo /etc/init.d/e2guardian restart
