#!/bin/bash

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
CONTENT="${*}"
PROXIED="true"
TTL="1"
#    -H "X-Auth-Key: ${KEY}" \
curl -X POST "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records/" \
    -H "X-Auth-Email: ${EMAIL}" \
    -H "Authorization: Bearer ${KEY}" \
    -H "Content-Type: application/json" \
    --data '{"type":"'"${TYPE}"'","name":"'"${NAME}"'","content":"'"${CONTENT}"'","proxied":'"${PROXIED}"',"ttl":'"${TTL}"'}' \
    | python -m json.tool;
