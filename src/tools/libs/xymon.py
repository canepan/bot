import logging
import os
import socket
from subprocess import check_output

APP_NAME = "XymonLib"


class XymonStatus(Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class Xymon(object):
    GREEN = 0
    YELLOW = 1
    RED = 2
    STATUS = ["green", "yellow", "red"]

    def __init__(self, cfg, check_name):
        os.environ["PATH"] += ":/usr/lib/xymon/client/bin"
        self.check_name = check_name
        self.host = (os.environ.get('CLIENTHOSTNAME', None) or socket.getfqdn()).replace(".", ",")
        self.debug = cfg.debug
        self._log = logging.getLogger("{}.{}".format(APP_NAME, self.__class__.__name__))

    def send_status(self, status: XymonStatus, message: str):
        if self.debug:
            debug = ["echo"]
        else:
            debug = []
        for dest in os.environ.get("XYMONSERVERS", "192.168.0.68").split():
            self._log.debug("Sending %s: %s\nfor %s to %s", Xymon.STATUS[status], message, self.host, dest)
            self._log.info(
                check_output(
                    debug
                    + [
                        "xymon",
                        dest,
                        "status {}.{} {} {}\n{}".format(
                            self.host,
                            self.check_name,
                            status.value,
                            time.asctime(),
                            message,
                        ),
                    ]
                )
            )



