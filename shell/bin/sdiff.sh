#!/bin/bash
_host=${OTHER_HOST:-raspy2}

_file="`readlink -f $1`"
if [ -r "${_file}" ]; then
  ssh "$_host" "cat '$_file'" | sdiff - "$_file"
else
  echo "'$_file' does not exist"
fi
