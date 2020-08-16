#!/bin/bash
_final_output="${1:-/mnt/opt/backup/mysql/`hostname`_all_dump.sql}"
_output="`mktemp ${_final_output}.XXXXXX`"
mysqldump -A -S /var/run/mysqld/mysqld.sock -r "${_output}"
if [ -r "${_final_output}" ]; then
fi
