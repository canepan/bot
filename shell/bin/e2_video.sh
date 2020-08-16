#!/bin/bash
case "$1" in
  enable)
    /usr/local/bin/configure_e2g -c /etc/squidguard/kids_allow_video.cfg --unsafe
    /usr/local/bin/configure_e2g -c /etc/e2guardian/kids_allow_video.cfg --unsafe
    [ $? -ne 0 ] && exit 0
    ;;
  disable)
    /usr/local/bin/configure_e2g -c /etc/squidguard/kids.cfg --unsafe
    /usr/local/bin/configure_e2g -c /etc/e2guardian/kids.cfg --unsafe
    [ $? -ne 0 ] && exit 0
    ;;
  *)
    echo "$0 enable|disable"
    exit 1
    ;;
esac
sudo /etc/init.d/e2guardian restart
