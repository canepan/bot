#!/bin/sh
[ $# -eq 0 ] && echo "Specify service (homenet or undo)" && exit 1

_libdir="$(readlink -f $(dirname $0)/../lib)"
_basename="$(basename $0 .sh)"

[ -r "${_libdir}/${_basename}_lib.sh" ] && . "${_libdir}/${_basename}_lib.sh"

is_proxy || exit 0

sleep_date() {
  [ -z "$NOSLEEP" ] && sleep $1
  /bin/echo -n "`date +%Y%m%d%H%M%S` - "
}

case "$1" in
  homenet)
# changed 9 Dec 2019
#    ( sleep_date 30 ; curl -s "http://freedns.afraid.org/dynamic/update.php?d05BTnNEd1UwbW1Rbzd0THFYYnU6MTA5MzkxNDY=" ) >> /tmp/freedns_canne_homenet_org.log 2>&1
# changed 15 August 2020
#    ( sleep_date 30 ; curl -s "http://freedns.afraid.org/dynamic/update.php?TG9KQ3h4TVdlWlkyZUl3RUI3Qm86MTA5MzkxNDY=" ) >> /tmp/freedns_canne_homenet_org.log 2>&1
    ( sleep_date 30 ; curl -s "http://sync.afraid.org/u/knLYa9HWgR4mSrWmndjuWGh7/" ) >> /tmp/freedns_canne_homenet_org.log 2>&1
    ;;
  undo)
# changed 9 Dec 2019
#    ( sleep_date 50 ; curl -s "http://freedns.afraid.org/dynamic/update.php?d05BTnNEd1UwbW1Rbzd0THFYYnU6MTE0ODEwMDc=" ) >> /tmp/freedns_canne_undo_it.log 2>&1
# changed 15 August 2020
#    ( sleep_date 50 ; curl -s "http://freedns.afraid.org/dynamic/update.php?TG9KQ3h4TVdlWlkyZUl3RUI3Qm86MTE0ODEwMDc=" ) >> /tmp/freedns_canne_undo_it.log 2>&1
    ( sleep_date 50 ; curl -s "http://sync.afraid.org/u/7oBYGvfaDSMUpDo8rTnqTSTr/" ) >> /tmp/freedns_canne_undo_it.log 2>&1
    ;;
esac

