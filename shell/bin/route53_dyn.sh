#!/bin/bash

# (optional) You might need to set your PATH variable at the top here
# depending on how you run this script
#PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
PATH="$HOME/bin":/mnt/opt/nicola/aws/bin:$PATH

# Hosted Zone ID e.g. BJBK35SKMM9OE
ZONEID="`cat ${HOME}/.route53_zone_id`"

# The CNAME you want to update e.g. hello.example.com
RECORDSET="www.nicolacanepa.net nicolacanepa.net fs.nicolacanepa.net apps.nicolacanepa.net ecommerce.nicolacanepa.net"

# More advanced options below
# The Time-To-Live of this recordset
TTL=300
# Change this if you want
COMMENT="Auto updating @ `date`"
# Change to AAAA if using an IPv6 address
TYPE="A"

# Get the external IP address from OpenDNS (more reliable than other providers)
#IP=`dig +short myip.opendns.com @resolver1.opendns.com`
IP=`curl -s http://ifconfig.co`

function valid_ip()
{
    local  ip=$1
    local  stat=1

    if [[ $ip =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
        OIFS=$IFS
        IFS='.'
        ip=($ip)
        IFS=$OIFS
        [[ ${ip[0]} -le 255 && ${ip[1]} -le 255 \
            && ${ip[2]} -le 255 && ${ip[3]} -le 255 ]]
        stat=$?
    fi
    return $stat
}

function _log() {
    cat | sed 's/^/'`date +%Y%m%d%H%M%S`' - /g' >> "$LOGFILE"
}

function _rotate() {
    _logfile="$1"
    _rlogfile="${_logfile}.`date +%Y%m%d%H%M%S`"
    mv -vi "${_logfile}" "${_rlogfile}"
    gzip -9 "${_rlogfile}"
}

# Get current dir
# (from http://stackoverflow.com/a/246128/920350)
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LOGFILE="$DIR/update-route53.log"

_logsize="`stat -c '%s' \"$LOGFILE\"`"
if [ $_logsize -gt 5242880 ]; then
    _rotate "$LOGFILE"
fi

for dnsname in $RECORDSET; do
  IPFILE="$DIR/update-route53-${dnsname}.ip"

  if ! valid_ip $IP; then
      echo "Invalid IP address: $IP" | _log
      #exit 1
      continue
  fi

  # Check if the IP has changed
  if [ ! -f "$IPFILE" ]
      then
      touch "$IPFILE"
  fi

  if grep -Fxq "$IP" "$IPFILE"; then
      # code if found
      echo "IP for $dnsname is still $IP. Exiting" | _log
      #exit 0
      continue
  else
      echo "IP for $dnsname has changed to $IP (from '`cat $IPFILE`')" | _log
      # Fill a temp file with valid JSON
      TMPFILE=$(mktemp /tmp/temporary-file.XXXXXXXX)
      cat > ${TMPFILE} << EOF
{
  "Comment":"$COMMENT",
  "Changes":[
    {
      "Action":"UPSERT",
      "ResourceRecordSet":{
        "ResourceRecords":[
          {
            "Value":"$IP"
          }
        ],
        "Name":"$dnsname",
        "Type":"$TYPE",
        "TTL":$TTL
      }
    }
  ]
}
EOF

      # Update the Hosted Zone record
      aws route53 change-resource-record-sets \
          --hosted-zone-id $ZONEID \
          --change-batch file://"$TMPFILE" | _log
      err=$?
      echo "" | _log

      # Clean up
      [ $err -eq 0 ] && rm $TMPFILE || echo "$TMPFILE not removed: check contents"
  fi

  # All Done - cache the IP address for next time
  [ $err -eq 0 ] && echo "$IP" > "$IPFILE"
done

