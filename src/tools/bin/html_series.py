#!/usr/bin/env python
import attr
import logging
import os
import sys
from argparse import Namespace

from tools.libs.parse_args import LoggingArgumentParser

TEMPLATE_PRE = '''<html>
  <head><title>{title}</title></head>
  <style>
    body {{ background-image: url(\'poster.jpg\'); }}
  </style>
  <body>
    <center>
      <img src="banner.jpg" /> <br/>
      <hr/>
'''
TEMPLATE_POST = '''
    </center>
  </body>
</html>'''
TEMPLATE_LINE = '      <a href="{season}/"><img src="season{season}-poster.jpg" height="300" /></a>'


def parse_args(argv: list) -> Namespace:
    parser = LoggingArgumentParser(app_name=__name__)
    parser.add_argument('series_dir', nargs='?', default=os.curdir)
    return parser.parse_args(argv)


@attr.s
class HtmlSeries(object):
    series_dir: str = attr.ib()
    log: logging.Logger = attr.ib()
    _seasons: list = None
    _html: str = None

    def check_dir(self) -> bool:
        result = True
        for fname in ('banner.jpg', 'poster.jpg'):
            full_path = os.path.join(self.series_dir, (fname))
            if not os.path.isfile(full_path):
                self.log.error(f'"{full_path}" not found')
                result = False
        return result

    def check_season(self, season: str) -> bool:
        try:
            int(season)
            season_poster = os.path.join(self.series_dir, f'season{season}-poster.jpg')
            if os.path.isfile(season_poster):
                return True
            self.log.info(f'"{season_poster}" not found')
            return False
        except Exception as e:
            self.log.debug(f'Exception for {season}: {e}')
            return False
        return True

    @property
    def seasons(self):
        if self._seasons is None:
            self._seasons = list()
            for _ , season_dirs, _ in os.walk(self.series_dir):
                self.log.debug(f'Found {season_dirs}')
                self._seasons.extend([s for s in season_dirs if self.check_season(s)])
                self._seasons.sort(key=int)
                break
        return self._seasons

    @property
    def html(self) -> str:
        if self._html is None:
            html_vars = {
                'title': os.path.basename(self.series_dir),
            }
            lines_list = list()
            for season in self.seasons:
                self.log.debug(f'Appending {season}')
                lines_list.append(TEMPLATE_LINE.format(season=season))
            lines = '\n'.join(lines_list)
            self._html = f'{TEMPLATE_PRE.format(**html_vars)}{lines}{TEMPLATE_POST}.format(**html_vars)'
        return self._html

    def save_html(self) -> bool:
        fname = os.path.join(self.series_dir, 'index.html')
        if os.path.isfile(fname):
            self.log.error(f'{fname} already exists')
            return False
        with open(fname, 'w') as f:
            f.write(self.html)
        return True


def main(argv: list = sys.argv[1:]):
    cfg = parse_args(argv)
    html_series = HtmlSeries(cfg.series_dir, cfg.log)
    if not html_series.check_dir():
        return 2
    cfg.log.debug(html_series.html)
    cfg.log.info(f'Saving index.html for {html_series}')
    if(html_series.save_html()):
        return 0
    return 3


if __name__ == '__main__':
    sys.exit(main())
