#!/bin/bash
grep -v -e closed$ -e '(uidNumber) not indexed' -e '(memberUid) not indexed'
