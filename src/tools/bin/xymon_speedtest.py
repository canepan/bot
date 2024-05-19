#!/usr/bin/python
import argparse
import gzip
import json
import logging
import os
import shutil
import socket
import subprocess
import time
from enum import Enum
from subprocess import check_output

from ..libs.xymon import Xymon, XymonStatus


APP_NAME = "Speedtest"
# 1MB
MAX_LOG_SIZE = 1048576


def tail(infile):
    with open(infile, "rb") as f:
        f.seek(-2, os.SEEK_END)  # Jump to the second last byte.
        while f.read(1) != b"\n":  # Until EOL is found...
            f.seek(-2, os.SEEK_CUR)  # ...jump back the read byte plus one more.
        last = f.readline()
    return last


def rotate_log(filename, max_log_size=MAX_LOG_SIZE):
    if os.path.isfile(filename):
        fstats = os.stat(filename)
        mtime = fstats.st_mtime
        size = fstats.st_size
        if size > max_log_size:
            with open(filename, "rb") as filein:
                gzfilename = "{}.gz".format(filename)
                with gzip.GzipFile(filename=gzfilename, mode="wb", mtime=mtime) as gzout:
                    shutil.copyfileobj(filein, gzout)
            os.unlink(filename)


def parse_line(line, log):
    if line is None:
        line = check_output(["/mnt/opt/venvs/speedtest/bin/speedtest", "--json"], universal_newlines=True).strip()
    log.debug("Read line: %s", line)
    return json.loads(line)


def main(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser(description="Monitor ISP speed")
    parser.add_argument(
        "--input_file",
        "-i",
        default="/var/lib/xymon/data/speedtest.log",
        help="Logfile with output line(s) from speedtest-cli",
    )
    parser.add_argument(
        "--debug", "-d", action="store_true", help="Enable debug (skips sending data)"
    )
    parser.add_argument(
        "--log_file",
        "-l",
        default="/var/log/xymon/speedtestpy.log",
        help="Logfile for speedtest.py",
    )
    cfg = parser.parse_args(argv)
    cfg.log = logging.getLogger(APP_NAME)
    if cfg.debug:
        cfg.log.setLevel(logging.DEBUG)
        cfg.log.addHandler(logging.StreamHandler())
    else:
        rotate_log(cfg.log_file)
        logging.basicConfig(filename=cfg.log_file)
        cfg.log.setLevel(logging.DEBUG)

    record = None
    try:
        record = parse_line(tail(cfg.input_file), log)
    except Exception as e:
        cfg.log.exception(e)
        record = parse_line(None)

    if record is None:
        record = {"upload": -1, "download": -1, "ping": -1}
    uspeed = record.get("upload", -1)
    dspeed = record.get("download", -1)
    if uspeed <= 0 or dspeed <= 0:
        status = XymonStatus.RED
    elif uspeed <= 100.0 * 1000 or dspeed <= 4.0 * 1000 * 1000:
        status = XymonStatus.YELLOW
    else:
        status = XymonStatus.GREEN
    Xymon(cfg, "ispeed").send_status(
        status,
        "upload_speed: {upload}\n"
        "download_speed: {download}\n"
        "ping: {ping}".format(**record),
    )


if __name__ == "__main__":
    main()
