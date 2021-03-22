import difflib
import logging


_log = logging.getLogger(__name__)


class CompareContents(object):
    def __init__(self, old_content: str, new_content: str, old_file_name='', new_file_name=''):
        self.old_content = old_content
        self.new_content = new_content
        self.extra_args = {}
        if old_file_name:
            self.extra_args['fromfile'] = old_file_name
        if new_file_name:
            self.extra_args['tofile'] = new_file_name
        _log.debug('CompareContent inited')

    def __repr__(self):
        return '\n'.join(
            difflib.unified_diff(self.old_content.splitlines(), self.new_content.splitlines(), n=1, **self.extra_args)
        )
