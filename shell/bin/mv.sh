#!/bin/bash
if [ $# -ne 2 ]; then
  echo "Specify source and dest"
  exit 1
fi
src=`readlink -f "$1"`
shift
dst=`readlink -f "$1"`
shift

dir_is_empty() {
  if [ "`ls -A \"$1\"`" ]; then
    return 1
  else
    return 0
  fi
}

if [ -d "$src" -a ! -r "$dst" ]; then
  _synoparam="-N"
elif [ -f "$src" -a ! -r "$dst" ]; then
  _synoparam="-n"
elif [ -f "$src" -a ! -r "${dst}/`basename \"${src}\"`" ]; then
  _synoparam="-n"
  dst="${dst}/`basename \"${src}\"`"
else
  echo "Source must be either files or dirs and dest must not exist"
  exit 2
fi
mv -vi "$src" "$dst"
srcdir="`dirname \"${src}\"`"
if dir_is_empty "$srcdir"; then
  echo "\'$srcdir\' is empty: removing"
  rmdir "$srcdir"
fi
synoindex $_synoparam "$dst" "$src"

