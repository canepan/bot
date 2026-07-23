"""macOS menu bar indicator showing when the network (ping to an IP) is unavailable.

Shows a green dot in the menu bar while the target host answers to ping, and a red
dot (plus an optional notification) when it stops answering.

By default it runs as a daemon (detached from the terminal, logging to
~/Library/Logs/net_watch.log); use --foreground to keep it attached.

Options can be set in ~/.config/net_watch.cfg (or a file passed with -c), e.g.:
    [net-watch]
    host = 192.168.1.1
    interval = 10
    failures = 3
    notifications = true

Requires the `rumps` package (macOS only): pip install rumps
"""

import configparser
import logging
import os
import subprocess
import sys
import typing

import click

try:
    import rumps
except ModuleNotFoundError:  # not on macOS, or extra not installed
    rumps = None

APP_NAME = 'net-watch'
DEFAULT_CONFIG = os.path.join('~', '.config', 'net_watch.cfg')
LOG_FILE = os.path.join('~', 'Library', 'Logs', 'net_watch.log')
OK_ICON = '\U0001f7e2'  # green circle
DOWN_ICON = '\U0001f534'  # red circle
_log = logging.getLogger(APP_NAME)


def ping_ok(host: str, timeout: int = 2) -> bool:
    """Return True if `host` answers a single ping within `timeout` seconds."""
    cmd = ['ping', '-c', '1', '-t', str(timeout), host]
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        _log.error('Error running %s: %s', ' '.join(cmd), e)
        return False
    return result.returncode == 0


class PingState(object):
    """Track consecutive ping failures and report up/down transitions.

    >>> state = PingState(failures=2)
    >>> state.update(False)  # first failure: still up
    >>> state.update(False)  # threshold reached: transition to down
    False
    >>> state.update(False)  # still down: no transition
    >>> state.update(True)  # transition to up
    True
    """

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.consecutive_failures = 0
        self.is_down = False

    def update(self, success: bool) -> typing.Optional[bool]:
        """Record a ping result; return True/False on transition to up/down, None otherwise."""
        if success:
            self.consecutive_failures = 0
            if self.is_down:
                self.is_down = False
                return True
        else:
            self.consecutive_failures += 1
            if not self.is_down and self.consecutive_failures >= self.failures:
                self.is_down = True
                return False
        return None


def notify(title: str, message: str) -> None:
    try:
        rumps.notification(title=title, subtitle='', message=message)
    except Exception as e:  # notifications need an app bundle: never break the app for this
        _log.warning('Unable to send notification: %s', e)


def run_app(host: str, interval: int, timeout: int, failures: int, notifications: bool) -> None:
    app = rumps.App('NetWatch', title=OK_ICON, quit_button='Quit')
    status_item = rumps.MenuItem(f'Target: {host}')
    last_item = rumps.MenuItem('No check yet')
    app.menu = [status_item, last_item]
    state = PingState(failures)

    def check(_timer: typing.Any) -> None:
        success = ping_ok(host, timeout)
        last_item.title = f'Last check: {"ok" if success else "FAILED"}'
        transition = state.update(success)
        if transition is False:
            app.title = DOWN_ICON
            _log.warning('%s unreachable', host)
            if notifications:
                notify('Network down', f'{host} is not answering to ping')
        elif transition is True:
            app.title = OK_ICON
            _log.info('%s reachable again', host)
            if notifications:
                notify('Network up', f'{host} is answering again')

    rumps.Timer(check, interval).start()
    app.run()


def daemonize() -> None:
    """Relaunch the same command detached from the terminal, with --foreground.

    A plain fork() is not safe with Objective-C frameworks (rumps/AppKit), so the
    process is re-executed in a new session instead.
    """
    log_path = os.path.expanduser(LOG_FILE)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'a') as log_file:
        process = subprocess.Popen(
            sys.argv + ['--foreground'],
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )
    click.echo(f'Started in background (pid {process.pid}), logging to {log_path}')


def load_config(ctx: click.Context, param: click.Parameter, value: str) -> str:
    """Read defaults from an INI file ([net-watch] section) into the context."""
    parser = configparser.ConfigParser()
    if parser.read(os.path.expanduser(value)) and parser.has_section(APP_NAME):
        ctx.default_map = dict(parser[APP_NAME])
    return value


@click.command()
@click.option(
    '-c',
    '--config',
    default=DEFAULT_CONFIG,
    show_default=True,
    callback=load_config,
    is_eager=True,
    expose_value=False,
    help='Config file (INI, [net-watch] section)',
)
@click.option('-H', '--host', default='1.1.1.1', show_default=True, help='IP or hostname to ping')
@click.option('-i', '--interval', default=5, show_default=True, help='Seconds between checks')
@click.option('-t', '--timeout', default=2, show_default=True, help='Ping timeout in seconds')
@click.option(
    '-f', '--failures', default=2, show_default=True, help='Consecutive failures before reporting the network as down'
)
@click.option('--notifications/--no-notifications', default=True, show_default=True, help='Notify on state change')
@click.option('-F', '--foreground', is_flag=True, help='Stay attached to the terminal (default: run as daemon)')
def main(host: str, interval: int, timeout: int, failures: int, notifications: bool, foreground: bool) -> None:
    """Show a menu bar icon reporting whether HOST answers to ping (macOS only)."""
    if rumps is None:
        raise click.ClickException('rumps is required (macOS only): pip install rumps')
    if foreground:
        logging.basicConfig(level=logging.INFO)
        run_app(host, interval, timeout, failures, notifications)
    else:
        daemonize()


if __name__ == '__main__':
    main()
