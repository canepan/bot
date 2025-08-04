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
    def __init__(self, input, filename=None):
        self.input = input
        self.buffer = b''
        self.zipper = GzipFile(filename, mode='wb', fileobj=self)

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
    parser = argparse.ArgumentParser(
        description='Backup all mysql DBs', formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('--output-file', default='/mnt/opt/backup/mysql/{}_all_dump.sql.gz'.format(os.uname().nodename))
    parser.add_argument('--mysql-socket', default='/var/run/mysqld/mysqld.sock')
    parser.add_argument('--debug', default='INFO', choices=('INFO', 'DEBUG', 'WARN', 'ERROR'))
    return parser.parse_args(argv)


class FileSize(object):
    def __init__(self, old_file: str, new_file: str):
        self.old_file = old_file
        self.new_file = new_file
        self._old_size = None
        self._new_size = None

    @property
    def old_size(self) -> int:
        if self._old_size is None:
            self._old_size = os.stat(self.old_file).st_size
        return self._old_size

    @property
    def new_size(self) -> int:
        if self._new_size is None:
            self._new_size = os.stat(self.new_file).st_size
        return self._new_size

    def size_difference_percent(self) -> float:
        return (self.new_size - self.old_size) / self.old_size


def main(argv: list = sys.argv[1:]):
    cfg = parse_args(argv)
    _log = logging.getLogger(__name__)
    _log.addHandler(logging.StreamHandler(sys.stdout))
    _log.setLevel(cfg.debug)

    _output = tempfile.NamedTemporaryFile(
        delete=False, dir=os.path.dirname(cfg.output_file), prefix=os.path.basename(cfg.output_file)
    )
    _log.info('Running mysqldump')
    command = subprocess.Popen(['mysqldump', '-A', '-S', cfg.mysql_socket], stdout=subprocess.PIPE)
    gzipstream = GzipStream(command.stdout)
    while command.poll() is None:
        _log.debug('Write chunk')
        _output.write(gzipstream.read())
    _log.debug('Last chunk')
    command.communicate()
    # If destination file already exists, save the old one if size if > 10% difference
    fsd = FileSize(cfg.output_file, _output.name)
    if os.path.isfile(cfg.output_file) and abs(fsd.size_difference_percent()) > 0.1:
        _log.debug('%s exists: checking', cfg.output_file)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        _log.info('Renaming %s to %s.%s', cfg.output_file, cfg.output_file, timestamp)
        os.rename(cfg.output_file, '{}.{}'.format(cfg.output_file, timestamp))
    if fsd.new_size > 0:
        _log.info('Renaming tempfile %s to %s', _output.name, cfg.output_file)
        os.rename(_output.name, cfg.output_file)
    else:
        _log.info('Removing empty tempfile')
        os.remove(_output.name)
    return 0


if __name__ == '__main__':
    sys.exit(main())
