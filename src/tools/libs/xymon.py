import logging
import os
import socket
import time
from enum import Enum
from subprocess import check_output

APP_NAME = "XymonLib"


class XymonStatus(Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class Xymon(object):
    def __init__(self, cfg, check_name):
        os.environ["PATH"] += ":/usr/lib/xymon/client/bin"
        self.check_name = check_name
        self.host = (os.environ.get('CLIENTHOSTNAME', None) or socket.getfqdn()).replace(".", ",")
        self.debug = cfg.debug
        self._log = logging.getLogger(f"{APP_NAME}.{self.__class__.__name__}")

    def send_status(self, status: XymonStatus, message: str):
        if self.debug:
            debug = ["echo"]
        else:
            debug = []
        for dest in os.environ.get("XYMONSERVERS", "192.168.0.68").split():
            text = f"status {self.host}.{self.check_name} {status.value} {time.asctime()}\n{message}"
            self._log.debug(f"Sending {status}: {message}\nfor {self.host} to {dest}")
            self._log.info(check_output(debug + ["xymon", dest, text]))

