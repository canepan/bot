config = {
    "on": (
        ("admin@mt", "/ip firewall address-list enable numbers=10,11,12,13"),
        ("root@phoenix", "grep -q '[^#].*192\.168\.19\.100' /etc/iptables/rules.v4 && "
         "(sed -i 's/^[^#].*192\.168\.19\.100/#\0/' /etc/iptables/rules.v4 && /etc/init.d/netfilter-persistent reload) "
         "; /usr/local/bin/e2_video.sh disable ; "
         "/usr/local/bin/manage_discord.py disable && /etc/init.d/e2guardian restart"),
    ),
    "off": (
        ("admin@mt", "/ip firewall address-list disable numbers=10,11,12,13"),
        ("root@phoenix", "grep -q '^#.*192\.168\.19\.100' /etc/iptables/rules.v4 && "
        "(sed -i 's/^#\(.*192\.168\.19\.100.*\)$/\1/' /etc/iptables/rules.v4 && "
        "/etc/init.d/netfilter-persistent reload) ; /usr/local/bin/e2_video.sh enable ; "
         "/usr/local/bin/manage_discord.py enable && /etc/init.d/e2guardian restart"),
    )
}
