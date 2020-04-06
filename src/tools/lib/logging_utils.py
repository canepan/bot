from logging import Filter


class MaxLevelFilter(Filter):
    '''Filters (lets through) all messages with level < LEVEL'''
    def __init__(self, level):
        self.level = level

    def filter(self, record):
        return record.levelno < self.level # "<" instead of "<=": since logger.setLevel is inclusive, this should be exclusive

