#!/bin/bash

# Temporary hack to use python script
"$(dirname $0)/cloudflare_dns.py" update -A -U "${@}"
exit $?

if [ -r "${HOME}/.cloudflare" ]; then
  . "${HOME}/.cloudflare"
else
  echo "Please add cloudflare_key and cloudflare_zone_id variables to '${HOME}/.cloudflare'"
  exit 1
fi

EMAIL="canne74@gmail.com"
KEY="${cloudflare_key}"
ZONE_ID="${cloudflare_zone_id}"
TYPE="A"
NAME="www.nicolacanepa.net"
RECORD_ID="5c79dcb9419a6d7c2afb5f510f3d09a3"
CONTENT="${*}"
PROXIED="true"
TTL="1"
#    -H "X-Auth-Key: ${KEY}" \
# With POST record is added, with PUT it should be updated
# curl -s -X POST "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records/" \
curl -s -X PUT "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records/${RECORD_ID}" \
    -H "X-Auth-Email: ${EMAIL}" \
    -H "Authorization: Bearer ${KEY}" \
    -H "Content-Type: application/json" \
    --data '{"type":"'"${TYPE}"'","name":"'"${NAME}"'","content":"'"${CONTENT}"'","proxied":'"${PROXIED}"',"ttl":'"${TTL}"'}' \
    | python -m json.tool;
