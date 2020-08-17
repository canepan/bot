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


def _stream_handler(logstream, loglevel, logname, logfilters=None) -> logging.Handler:
    handler = logging.StreamHandler(logstream)
    handler.setLevel(loglevel)
    handler.set_name(logname)
    for logfilter in logfilters or []:
        handler.addFilter(logfilter)
    return handler


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
    stderr_handler = _stream_handler(logstream=sys.stderr, loglevel=logging.INFO, logname='stderr')
    log.addHandler(stderr_handler)
    stdout_handler = _stream_handler(
        logstream=sys.stdout, loglevel=logging.INFO, logname='stdout', logfilters=[MaxLevelFilter(logging.INFO)]
    )
    log.addHandler(stdout_handler)
    if verbose:
        loglevel = logging.DEBUG
    elif quiet:
        loglevel = logging.ERROR
    else:
        loglevel = logging.INFO
    if with_file:
        logfile = logging.FileHandler(with_file)
        logfile.setLevel(logging.DEBUG)
        logfile.set_name('logfile')
        log.addHandler(logfile)
        logfile.setFormatter(LOG_FORMATTER)
        log.setLevel(logging.DEBUG)
        stderr_handler.setLevel(loglevel)
    else:
        stdout_handler.setFormatter(LOG_FORMATTER)
        stderr_handler.setFormatter(LOG_FORMATTER)
        log.setLevel(loglevel)
    return log
