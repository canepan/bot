#!/usr/bin/env python3
"""
Xymon check: verify that the public IPv4 address (as reported by https://ifconfig.io)
matches the IPv4 address returned by an external DNS resolver for www.nicolacanepa.net.
Uses dnspython for external DNS queries and the Xymon library for status reporting.
"""

import sys
import urllib.request
import logging
from typing import Optional

try:
    import dns.resolver
except ImportError:
    dns = None

try:
    from ..libs.xymon import Xymon, XymonStatus
except (ImportError, ValueError):
    from tools.libs.xymon import Xymon, XymonStatus

APP_NAME = "IPCheck"
HOSTNAME = "www.nicolacanepa.net"
DEFAULT_DNS = "8.8.8.8"


def get_public_ip() -> str:
    with urllib.request.urlopen("https://ifconfig.io/ip", timeout=5) as resp:
        return resp.read().decode().strip()


def query_dns_external(ip_resolver: str, name: str) -> Optional[str]:
    if dns is None:
        return None
    resolver = dns.resolver.Resolver()
    resolver.nameservers = [ip_resolver]
    resolver.timeout = 5
    try:
        answer = resolver.resolve(name, "A")
        return str(answer[0])
    except Exception:
        return None


def main(argv: list = sys.argv[1:]):
    dns_server = sys.getenv("EXTERNAL_DNS", DEFAULT_DNS)
    public_ip = get_public_ip()
    dns_ip = query_dns_external(dns_server, HOSTNAME)

    cfg = type("Cfg", (), {})()
    cfg.debug = False
    cfg.log = logging.getLogger(APP_NAME)
    if not cfg.log.handlers:
        cfg.log.addHandler(logging.NullHandler())

    if dns_ip is None:
        Xymon(cfg, APP_NAME, "ip").send_status(
            XymonStatus.RED,
            f"CRITICAL - DNS lookup failed for {HOSTNAME} using {dns_server}\n"
        )
        sys.exit(2)

    if public_ip == dns_ip:
        status = XymonStatus.GREEN
        msg = f"OK - Public IP {public_ip} matches DNS {dns_ip}\n"
    else:
        status = XymonStatus.YELLOW
        msg = f"WARNING - Public IP {public_ip} differs from DNS {dns_ip}\n"

    Xymon(cfg, APP_NAME, "ip").send_status(status, msg)
    sys.exit(0 if status == XymonStatus.GREEN else 1)


if __name__ == "__main__":
    main()