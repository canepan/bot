#!/bin/bash
# tool to start a service. Workflow is:
#  * get config from git
#  * backup current config (with timestamp) if different
#  * apply config
#  * check if primary (VRRP IP)
#  * start as a primary or (if possible) as secondary

function git_pull() {
  _tmpdir="${1}"
  cd "${_tmpdir}"
}

function backup_config() {
  true
}

function apply_config() {
  true
}

function start_pri_or_sec() {
  true
}


function start() {
  _tmpdir="$(mktemp -d)"
  git_pull "${_tmpdir}"
  backup_config
  apply_config
  start_pri_or_sec
}
