#!/usr/bin/env python3
import argparse
import logging
import sys
import os
import subprocess
import tempfile
from gzip import GzipFile
from datetime import datetime


class GzipStream(object):
    # input is a filelike object that feeds the input
    def __init__(self, input, filename = None):
        self.input = input
        self.buffer = b''
        self.zipper = GzipFile(filename, mode = 'wb', fileobj = self)

    def read(self, size=-1):
        if (size < 0) or len(self.buffer) < size:
            for s in self.input:
                self.zipper.write(s)
                if size > 0 and len(self.buffer) >= size:
                    self.zipper.flush()
                    break
            else:
                self.zipper.close()
            if size < 0:
                ret = self.buffer
                self.buffer = b''
        else:
            ret, self.buffer = self.buffer[:size], self.buffer[size:]
        return ret

    def flush(self):
        pass

    def write(self, data):
        self.buffer += data

    def close(self):
        self.input.close()


def parse_args(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='Backup all mysql DBs', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--output-file', default='/mnt/opt/backup/mysql/{}_all_dump.sql.gz'.format(os.uname().nodename))
    parser.add_argument('--mysql-socket', default='/var/run/mysqld/mysqld.sock')
    parser.add_argument('--debug', default='INFO', choices=('INFO', 'DEBUG', 'WARN', 'ERROR'))
    return parser.parse_args(argv)


def main(argv: list = sys.argv[1:]):
    cfg = parse_args()
    _log = logging.getLogger(__name__)
    _log.addHandler(logging.StreamHandler(sys.stdout))
    _log.setLevel(cfg.debug)

    _output = tempfile.NamedTemporaryFile(delete=False, dir=os.path.dirname(cfg.output_file), prefix=os.path.basename(cfg.output_file))
    _log.info('Running mysqldump')
    command = subprocess.Popen(['mysqldump', '-A', '-S', cfg.mysql_socket], stdout=subprocess.PIPE)
    gzipstream = GzipStream(command.stdout)
    while command.poll() is None:
        _log.debug('Write chunk')
        _output.write(gzipstream.read())
    _log.debug('Last chunk')
    command.communicate()
    if os.path.isfile(cfg.output_file):
        _log.info('%s exists: checking', cfg.output_file)
        new_size = os.stat(_output.name).st_size
        old_size = os.stat(cfg.output_file).st_size
        if abs(new_size - old_size) > 0.1 * old_size:
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            _log.info('Renaming %s to %s.%s', cfg.output_file, cfg.output_file, timestamp)
            os.rename(cfg.output_file, '{}.{}'.format(cfg.output_file, timestamp))
        if new_size > 0:
            _log.info('Renaming tempfile %s to %s', _output.name, cfg.output_file)
            os.rename(_output.name, cfg.output_file)
        else:
            _log.info('Removing empty tempfile')
            os.remove(_output.name)
    return 0


if __name__ == '__main__':
    sys.exit(main())
