import subprocess
import socket


def is_proxy() -> bool:
    _proxy_ip = socket.gethostbyname('proxy')
    out = subprocess.check_output(['/sbin/ip', '-o', 'addr']).decode('utf-8')
    for line in out.splitlines():
        if _proxy_ip in line:
            return True
    return False
