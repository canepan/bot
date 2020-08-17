import logging
import sys

LOG_FORMATTER = logging.Formatter(
    fmt='%(asctime)s %(name)s:%(module)s:%(funcName)s:%(lineno)d %(message)s',
    datefmt='%Y%m%d%H%M%S'
)


class MaxLevelFilter(logging.Filter):
    '''Filters (lets through) all messages with level < LEVEL'''
    def __init__(self, level):
        self.level = level

    def filter(self, record):
        return record.levelno < self.level # "<" instead of "<=": since logger.setLevel is inclusive, this should be exclusive


def get_logger(app_name: str, verbose: bool, quiet: bool, with_file: str = None):
    """
    Sets format to '%(asctime)s %(name)s:%(module)s:%(funcName)s:%(lineno)d %(message)s'  and datefmt to '%Y%m%d%H%M%S',
      either on stdout and stderr or (if set) in the logfile
    Logging format
      %(name)s            Name of the logger (logging channel)
      %(module)s          Module (name portion of filename)
      %(lineno)d          Source line number where the logging call was issued
                          (if available)
      %(funcName)s        Function name
      %(asctime)s         Textual time when the LogRecord was created
      %(process)d         Process ID (if available)
      %(message)s         The result of record.getMessage(), computed just as
                          the record is emitted
    """
    log = logging.getLogger(app_name)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.INFO)
    stderr_handler.set_name('stderr')
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.addFilter(MaxLevelFilter(logging.INFO))
    stdout_handler.set_name('stdout')
    log.addHandler(stderr_handler)
    log.addHandler(stdout_handler)
    log.setLevel(logging.DEBUG)
    if verbose:
        stdout_handler.setLevel(logging.DEBUG)
        stderr_handler.setLevel(logging.DEBUG)
    elif quiet:
        stdout_handler.setLevel(logging.ERROR)
        stderr_handler.setLevel(logging.ERROR)
    else:
        stdout_handler.setLevel(logging.INFO)
        stderr_handler.setLevel(logging.INFO)
    if with_file:
        logfile = logging.FileHandler(with_file)
        logfile.setLevel(logging.DEBUG)
        logfile.set_name('logfile')
        log.addHandler(logfile)
        logfile.setFormatter(LOG_FORMATTER)
    else:
        stdout_handler.setFormatter(LOG_FORMATTER)
        stderr_handler.setFormatter(LOG_FORMATTER)
    return log
