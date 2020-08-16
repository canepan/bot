#!/bin/bash
rsync -rtni "$@" | grep -e '^[<>c*].c' -e '^[<>c*]..s'
if [ $? -eq 0 ]; then
  cat <<EOD
Legend: each line in the format
YXcstpoguax FILENAME
 Y: '
  o < file to be transferred to remote (sent).
  o > file to be transferred to local (received).
  o c local change/creation for the item (create a dir, change a symlink, etc.).
  o h hard link to another item (requires --hard-links).
  o . not being updated (though it might have attributes that are being modified).
  o * the rest of the itemized-output area contains a message (e.g. "deleting").
 X: f - file, d - dir, L - symlink, D - device, S - special file
 Checksum, Size, Time, Perms, Owner, Group, U?, Acl, eXtended attrs
EOD
else
  echo "No difference for $*"
fi
