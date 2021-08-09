#!/bin/bash
for _host in ${@:-quark bigmac foo www.nicolacanepa.net}; do
#  ping -c2 -W1 "${_host}" &> /dev/null || continue
  ssh -o 'ConnectTimeout 2' -q "${_host}" hostname || continue
  for _src in "${HOME}/Documents/Nicola.kdbx" "${HOME}/Documents/Nicola/Nicola_pass.kdbx"; do
    _basename=`basename "${_src}" .kdbx`
    _dest="Documents/Nicola/${_basename}-`date +%Y%m%d`.kdbx"
    _linksrc="`basename ${_dest}`"
    _linkdest="Documents/Nicola/${_basename}.kdbx"
    _passwords="Documents/Nicola/password"
    echo "${_src} -> ${_host}:${_dest}"
    [ -z "$DEBUG" ] && scp -p "${_src}" ${_host}:"${_dest}"
    ssh -q "${_host}" "
        hostname
        if ls -l ${_dest}; then
          _currlink=\"\`readlink -n ${_linkdest}\`\"
          echo \$_currlink
          if [ ! -e ${_linkdest} -o -h ${_linkdest} ]; then
            ln -vsf ${_linksrc} ${_linkdest} && [ \"\$_currlink\" != \"${_linksrc}\" ] && mv -vi Documents/Nicola/\"\$_currlink\" ${_passwords}/
          fi
        fi
    "
  done
done

