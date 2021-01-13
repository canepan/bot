#!/bin/bash
_script="`dirname $0`/`basename $0 .sh`.py"
output="`${_script}`"
if [ -n "${output}" ]; then
  echo "${output}" | mail -s "Proxy breach" canne74@gmail.com
fi
