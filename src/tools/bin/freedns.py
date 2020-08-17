#!/mnt/opt/nicola/tools/bin/python
import configargparse as argparse
import logging
import os
import re
import sys
import time
from datetime import datetime
from urllib import request

from ..libs.parse_args import with_quiet_verbose
from ..libs.vip_utils import is_proxy

APP_NAME = 'tools.FreeDNS'
SLEEP_TIME = 30
_log = logging.getLogger(APP_NAME)


def parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Update Afraid FreeDNS record(s)',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('service', choices=['homenet', 'undo'])
    parser.add_argument('--unsafe', action='store_true', help='Really write/rename files')
    return with_quiet_verbose(app_name=APP_NAME, parser=parser, argv=argv, logfile='/tmp/afraid_{service}.log')


def sleep(sleep_time: int = SLEEP_TIME, unsafe: bool = False):
    if unsafe and not os.environ.get('NOSLEEP'):
        time.sleep(sleep_time)


def update_afraid(afraid_key: str, unsafe: bool = False, _log:logging.Logger = _log) -> bool:
    """:returns: True if the record was changed, False otherwise"""
    sleep(unsafe=unsafe)
    full_url = "http://sync.afraid.org/u/{}".format(afraid_key)
    if unsafe:
        http_result = request.urlopen(full_url)
        content = http_result.read().decode('utf-8').strip()
        _log.debug(content)
        return http_result.status == 200 and re.match(r'Updated .* from', content)
    else:
        _log.info('Would have called: %s', full_url)
        return True


def main(argv=sys.argv[1:]):
    cfg = parse_args(argv)
    if is_proxy():
        if cfg.service == 'homenet':
            # changed 9 Dec 2019
            # http://freedns.afraid.org/dynamic/update.php?d05BTnNEd1UwbW1Rbzd0THFYYnU6MTA5MzkxNDY=
            # changed 15 August 2020
            # http://freedns.afraid.org/dynamic/update.php?TG9KQ3h4TVdlWlkyZUl3RUI3Qm86MTA5MzkxNDY=
            if update_afraid(afraid_key="knLYa9HWgR4mSrWmndjuWGh7/", unsafe=cfg.unsafe):
                cfg.log.info('homenet updated')
                return 0
            else:
                cfg.log.debug('homenet untouched')
                return 1
                
            # >> /tmp/freedns_canne_homenet_org.log 2>&1
        if cfg.service == 'undo':
            # changed 9 Dec 2019
            # http://freedns.afraid.org/dynamic/update.php?d05BTnNEd1UwbW1Rbzd0THFYYnU6MTE0ODEwMDc=
            # changed 15 August 2020
            # http://freedns.afraid.org/dynamic/update.php?TG9KQ3h4TVdlWlkyZUl3RUI3Qm86MTE0ODEwMDc=
            if update_afraid(afraid_key="7oBYGvfaDSMUpDo8rTnqTSTr/", unsafe=cfg.unsafe):
                cfg.log.info('undo updated')
                return 0
            else:
                cfg.log.debug('undo untouched')
                return 2


if __name__ == '__main__':
    sys.exit(main())
