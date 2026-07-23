"""macOS menu bar indicator showing when the network is unavailable.

Checks a target periodically (ping for an IP/hostname, HTTP GET if the target is a
URL) and shows a green dot in the menu bar while it answers, a red dot (plus an
optional notification) when it stops answering. The menu also shows failure stats
(failed/total checks and percentage).

By default it runs as a daemon (detached from the terminal, logging to
~/Library/Logs/net_watch.log); use --foreground to keep it attached, --kill to
stop the running instance.

Options can be set in ~/.config/net_watch.cfg (or a file passed with -c), e.g.:
    [net-watch]
    host = https://www.google.com
    interval = 10
    failures = 3
    notifications = true

Requires the `rumps` package (macOS only): pip install rumps
"""

import atexit
import configparser
import logging
import os
import signal
import subprocess
import sys
import typing
from pathlib import Path

import click
import requests

try:
    import rumps
except ModuleNotFoundError:  # not on macOS, or extra not installed
    rumps = None

APP_NAME = 'net-watch'
DEFAULT_CONFIG = Path('~', '.config', 'net_watch.cfg')
LOG_FILE = Path('~', 'Library', 'Logs', 'net_watch.log')
PID_FILE = Path('~', 'Library', 'Caches', 'net_watch.pid')
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


def http_ok(url: str, timeout: int = 2) -> bool:
    """Return True if `url` answers an HTTP GET with a non-error status within `timeout` seconds."""
    try:
        return requests.get(url, timeout=timeout).ok
    except requests.RequestException as e:
        _log.error('Error requesting %s: %s', url, e)
        return False


def check_ok(target: str, timeout: int) -> bool:
    """Check `target` with HTTP GET if it is a URL, with ping otherwise."""
    if target.startswith(('http://', 'https://')):
        return http_ok(target, timeout)
    return ping_ok(target, timeout)


class CheckState(object):
    """Track consecutive failures, report up/down transitions and collect stats.

    >>> state = CheckState(failures=2)
    >>> state.update(False)  # first failure: still up
    >>> state.update(False)  # threshold reached: transition to down
    False
    >>> state.update(False)  # still down: no transition
    >>> state.update(True)  # transition to up
    True
    >>> state.failed, state.total
    (3, 4)
    >>> state.failure_pct
    75.0
    """

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.consecutive_failures = 0
        self.is_down = False
        self.total = 0
        self.failed = 0

    @property
    def failure_pct(self) -> float:
        return 100.0 * self.failed / self.total if self.total else 0.0

    def update(self, success: bool) -> typing.Optional[bool]:
        """Record a check result; return True/False on transition to up/down, None otherwise."""
        self.total += 1
        if success:
            self.consecutive_failures = 0
            if self.is_down:
                self.is_down = False
                return True
        else:
            self.failed += 1
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


def remove_pid_file() -> None:
    PID_FILE.expanduser().unlink(missing_ok=True)


def write_pid_file() -> None:
    pid_path = PID_FILE.expanduser()
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()))
    atexit.register(remove_pid_file)


def kill_running() -> None:
    """Stop the running instance using the pid file."""
    pid_path = PID_FILE.expanduser()
    try:
        pid = int(pid_path.read_text().strip())
    except (OSError, ValueError):
        raise click.ClickException(f'No running instance found ({pid_path} missing or invalid)')
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        remove_pid_file()
        raise click.ClickException(f'Process {pid} not running: removed stale pid file')
    remove_pid_file()
    click.echo(f'Stopped {APP_NAME} (pid {pid})')


def run_app(host: str, interval: int, timeout: int, failures: int, notifications: bool) -> None:
    write_pid_file()
    signal.signal(signal.SIGTERM, lambda *_: rumps.quit_application())
    app = rumps.App('NetWatch', title=OK_ICON, quit_button='Quit')
    status_item = rumps.MenuItem(f'Target: {host}')
    last_item = rumps.MenuItem('No check yet')
    stats_item = rumps.MenuItem('No stats yet')
    app.menu = [status_item, last_item, stats_item]
    state = CheckState(failures)

    def check(_timer: typing.Any) -> None:
        success = check_ok(host, timeout)
        transition = state.update(success)
        last_item.title = f'Last check: {"ok" if success else "FAILED"}'
        stats_item.title = f'Failures: {state.failed}/{state.total} ({state.failure_pct:.1f}%)'
        if transition is False:
            app.title = DOWN_ICON
            _log.warning('%s unreachable', host)
            if notifications:
                notify('Network down', f'{host} is not answering')
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
    log_path = LOG_FILE.expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('a') as log_file:
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
    if parser.read(Path(value).expanduser()) and parser.has_section(APP_NAME):
        ctx.default_map = dict(parser[APP_NAME])
    return value


@click.command()
@click.option(
    '-c',
    '--config',
    default=str(DEFAULT_CONFIG),
    show_default=True,
    callback=load_config,
    is_eager=True,
    expose_value=False,
    help='Config file (INI, [net-watch] section)',
)
@click.option(
    '-H', '--host', default='1.1.1.1', show_default=True, help='IP/hostname to ping, or URL (http[s]://) to GET'
)
@click.option('-i', '--interval', default=5, show_default=True, help='Seconds between checks')
@click.option('-t', '--timeout', default=2, show_default=True, help='Check timeout in seconds')
@click.option(
    '-f', '--failures', default=2, show_default=True, help='Consecutive failures before reporting the network as down'
)
@click.option('--notifications/--no-notifications', default=True, show_default=True, help='Notify on state change')
@click.option('-F', '--foreground', is_flag=True, help='Stay attached to the terminal (default: run as daemon)')
@click.option('--kill', is_flag=True, help='Stop the running instance and exit')
def main(
    host: str, interval: int, timeout: int, failures: int, notifications: bool, foreground: bool, kill: bool
) -> None:
    """Show a menu bar icon reporting whether HOST answers to ping/HTTP (macOS only)."""
    if kill:
        kill_running()
        return
    if rumps is None:
        raise click.ClickException('rumps is required (macOS only): pip install rumps')
    if foreground:
        logging.basicConfig(level=logging.INFO)
        run_app(host, interval, timeout, failures, notifications)
    else:
        daemonize()


if __name__ == '__main__':
    main()
