#!/bin/bash
sed 's/^/'$(date +%Y%m%d%H%M%S)' - /'
