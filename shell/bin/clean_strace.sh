#!/bin/sh
grep -v -e 'mprotect resumed' -e 'rt_sigaction resumed' -e 'wait resumed' -e mmap -e rt_sigaction -e mprotect -e munmap
