"""Detect TCP disconnections between the LAN and the internet.

Holds a single persistent keep-alive TLS connection to a target (by default
``www.nicolacanepa.net:443``), optionally routed through an HTTP CONNECT proxy,
and sends a lightweight ``HEAD`` heartbeat on that same connection every few
seconds. When the connection drops (RST/FIN/timeout/HTTP 5xx) it records the
event -- with how long the connection had been up and the failure reason -- to
an evidence-trail logfile and (optionally) to Xymon, then reconnects.

Why a proxy: connecting directly to your own public name may be hairpinned by
the router (NAT loopback) and never traverse the WAN. Routing through an
external CONNECT proxy forces the persistent connection out over the WAN, so a
drop reflects a real internet-path event.

Optional pre/post hooks wrap the connection lifecycle: the pre-script runs
before (re)connecting (e.g. bring a VPN up so the target is reachable from
outside), the post-script runs after the connection is torn down and on exit
(e.g. tear the VPN down). They are kept paired with the connection state.

By default it runs detached (daemon), logging to
``~/.local/state/tcp_persist_monitor.log``; use ``--foreground`` to stay
attached (e.g. under systemd), ``--kill`` to stop the running instance.

Options can be set in ``~/.config/tcp_persist_monitor.cfg`` (or a file passed
with ``-c``), e.g.::

    [tcp-persist-monitor]
    target_host = www.nicolacanepa.net
    proxy_host = vps.example.net
    proxy_port = 8080
    heartbeat = 30
    pre_script = wg-quick up wg0
    post_script = wg-quick down wg0
"""

from __future__ import annotations

import atexit
import base64
import configparser
import dataclasses
import http.client
import logging
import os
import signal
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path

import click

try:
    from ..libs.logging_utils import get_logger
    from ..libs.xymon import Xymon, XymonStatus
except (ImportError, ValueError):
    from tools.libs.logging_utils import get_logger
    from tools.libs.xymon import Xymon, XymonStatus

APP_NAME = 'tcp-persist-monitor'
DEFAULT_CONFIG = Path('~', '.config', 'tcp_persist_monitor.cfg')
LOG_FILE = Path('~', '.local', 'state', 'tcp_persist_monitor.log')
PID_FILE = Path('~', '.cache', 'tcp_persist_monitor.pid')
_log = logging.getLogger(APP_NAME)


@dataclasses.dataclass
class MonitorConfig:
    """Runtime configuration passed to the monitor and the Xymon helper."""

    target_host: str
    target_port: int
    path: str
    proxy_host: str | None
    proxy_port: int
    proxy_auth: str | None
    heartbeat: int
    timeout: int
    reconnect_delay: int
    pre_script: str | None
    post_script: str | None
    hook_timeout: int
    tls: bool
    verify_tls: bool
    xymon: bool
    xymon_check: str
    debug: bool
    log: logging.Logger


class ConnectionTracker:
    """Track up/down transitions and count disconnects.

    Returns ``True`` only on a state change, so callers report once per
    transition rather than on every heartbeat.

    >>> t = ConnectionTracker()
    >>> t.mark_up()      # first success: transition to up
    True
    >>> t.mark_up()      # already up: no transition
    False
    >>> t.mark_down()    # transition to down
    True
    >>> t.mark_down()    # still down: no transition
    False
    >>> t.mark_up()      # recovery
    True
    >>> (t.connects, t.disconnects)
    (2, 1)
    """

    def __init__(self) -> None:
        self.is_up: bool | None = None
        self.connects = 0
        self.disconnects = 0

    def mark_up(self) -> bool:
        if self.is_up is True:
            return False
        self.is_up = True
        self.connects += 1
        return True

    def mark_down(self) -> bool:
        if self.is_up is False:
            return False
        self.is_up = False
        self.disconnects += 1
        return True


def _ssl_context(cfg: MonitorConfig) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if not cfg.verify_tls:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def _proxy_headers(cfg: MonitorConfig) -> dict[str, str]:
    if cfg.proxy_auth:
        token = base64.b64encode(cfg.proxy_auth.encode()).decode()
        return {'Proxy-Authorization': f'Basic {token}'}
    return {}


def route_description(cfg: MonitorConfig) -> str:
    """Human-readable description of the path being monitored.

    >>> log = logging.getLogger('doctest')
    >>> direct = MonitorConfig('h', 443, '/', None, 0, None, 30, 10, 2, None, None, 30, True, True, False, 'c', False, log)
    >>> route_description(direct)
    'h:443'
    >>> viaproxy = dataclasses.replace(direct, proxy_host='px', proxy_port=8080)
    >>> route_description(viaproxy)
    'px:8080 -> h:443'
    """
    target = f'{cfg.target_host}:{cfg.target_port}'
    if cfg.proxy_host:
        return f'{cfg.proxy_host}:{cfg.proxy_port} -> {target}'
    return target


def build_connection(cfg: MonitorConfig) -> http.client.HTTPConnection:
    """Construct (but do not yet dial) the keep-alive connection.

    Routing combinations:
    * TLS + proxy   -> connect to the proxy, arm a CONNECT tunnel to the target
    * TLS direct    -> connect straight to the target over HTTPS
    * HTTP + proxy  -> connect to the proxy; requests use the absolute-form URI
    * HTTP direct   -> connect straight to the target over plain HTTP

    Plain HTTP (``--no-tls``, e.g. port 80) avoids TLS/SNI and lets the server
    route by the Host header -- handy when split-horizon DNS forces a bare IP.
    """
    if cfg.tls:
        context = _ssl_context(cfg)
        if cfg.proxy_host:
            tunnel = http.client.HTTPSConnection(cfg.proxy_host, cfg.proxy_port, timeout=cfg.timeout, context=context)
            tunnel.set_tunnel(cfg.target_host, cfg.target_port, headers=_proxy_headers(cfg))
            return tunnel
        return http.client.HTTPSConnection(cfg.target_host, cfg.target_port, timeout=cfg.timeout, context=context)
    if cfg.proxy_host:
        return http.client.HTTPConnection(cfg.proxy_host, cfg.proxy_port, timeout=cfg.timeout)
    return http.client.HTTPConnection(cfg.target_host, cfg.target_port, timeout=cfg.timeout)


def probe(conn: http.client.HTTPConnection, cfg: MonitorConfig) -> int:
    """Send one heartbeat request on the open connection; raise on failure.

    The first call establishes the TLS/tunnel/keep-alive; subsequent calls reuse
    the same TCP connection, so a dropped connection surfaces here as an
    exception. A completed HTTP exchange (any status) means the connection is
    alive; only transport-level failures count as a drop.
    """
    headers = {'Host': cfg.target_host, 'Connection': 'keep-alive'}
    if cfg.proxy_host and not cfg.tls:
        # plain HTTP through a proxy: absolute-form request URI + proxy auth
        headers.update(_proxy_headers(cfg))
        target = f'http://{cfg.target_host}:{cfg.target_port}{cfg.path}'
    else:
        target = cfg.path
    conn.request('HEAD', target, headers=headers)
    resp = conn.getresponse()
    resp.read()
    # A completed HTTP exchange proves the TCP connection is alive; only
    # transport-level failures (which raise before we get here) count as a drop.
    # A 4xx/5xx is a server/app response, not a disconnection.
    if resp.status >= 400:
        cfg.log.debug('heartbeat returned HTTP %s (connection is alive)', resp.status)
    # keep the underlying socket alive at the TCP layer too
    try:
        conn.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)  # type: ignore[union-attr]
    except Exception:  # pragma: no cover - best effort
        pass
    return resp.status


def run_hook(command: str | None, cfg: MonitorConfig, label: str) -> None:
    """Run a pre/post shell hook (e.g. bring a VPN up/down); never raise."""
    if not command:
        return
    cfg.log.info('Running %s hook: %s', label, command)
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=cfg.hook_timeout)
    except Exception as e:
        cfg.log.error('%s hook failed to run: %s', label, e)
        return
    if result.returncode != 0:
        cfg.log.warning('%s hook exited %d: %s', label, result.returncode, result.stderr.strip())
    elif result.stdout.strip():
        cfg.log.debug('%s hook output: %s', label, result.stdout.strip())


def _emit(cfg: MonitorConfig, status: XymonStatus, message: str) -> None:
    if status == XymonStatus.GREEN:
        cfg.log.info(message)
    else:
        cfg.log.warning(message)
    if cfg.xymon:
        try:
            Xymon(cfg, APP_NAME, cfg.xymon_check).send_status(status, message)
        except Exception as e:  # never let a reporting failure kill the monitor
            cfg.log.error('Xymon report failed: %s', e)


def _close(conn: http.client.HTTPConnection | None) -> None:
    if conn is not None:
        try:
            conn.close()
        except Exception:  # pragma: no cover - best effort
            pass


def run_monitor(cfg: MonitorConfig, iterations: int | None = None) -> ConnectionTracker:
    """Main loop: hold the connection, heartbeat, log/report every disconnect.

    The pre-script runs before (re)connecting and the post-script after the
    connection is torn down and on exit, kept paired with the connection state.
    ``iterations`` bounds the loop for testing (``None`` = run forever).
    """
    tracker = ConnectionTracker()
    conn: http.client.HTTPConnection | None = None
    up_since: float | None = None
    hooked_up = False
    count = 0
    try:
        while iterations is None or count < iterations:
            count += 1
            try:
                if conn is None:
                    if not hooked_up:
                        run_hook(cfg.pre_script, cfg, 'pre')
                        hooked_up = True
                    conn = build_connection(cfg)
                probe_status = probe(conn, cfg)
                if tracker.mark_up():
                    up_since = time.time()
                    _emit(
                        cfg,
                        XymonStatus.GREEN,
                        f'connected {route_description(cfg)} HTTP {probe_status} (reconnects: {tracker.connects - 1})',
                    )
                time.sleep(cfg.heartbeat)
            except Exception as e:
                duration = int(time.time() - up_since) if up_since else 0
                if tracker.mark_down():
                    _emit(
                        cfg,
                        XymonStatus.RED,
                        f'TCP DISCONNECT on {route_description(cfg)} after {duration}s up: '
                        f'{type(e).__name__}: {e} (total disconnects: {tracker.disconnects})',
                    )
                _close(conn)
                conn = None
                up_since = None
                if hooked_up:
                    run_hook(cfg.post_script, cfg, 'post')
                    hooked_up = False
                time.sleep(cfg.reconnect_delay)
    finally:
        if hooked_up:
            run_hook(cfg.post_script, cfg, 'post')
    return tracker


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


def relaunch_command() -> list[str]:
    """The current command relaunched through the interpreter, in foreground mode."""
    return [sys.executable] + list(sys.argv) + ['--foreground']


def daemonize() -> None:
    """Relaunch the same command detached from the terminal, with --foreground."""
    log_path = LOG_FILE.expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        relaunch_command(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    click.echo(f'Started in background (pid {process.pid}), logging to {log_path}')


def load_config(ctx: click.Context, param: click.Parameter, value: str) -> str:
    """Read defaults from an INI file ([tcp-persist-monitor] section) into the context."""
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
    help='Config file (INI, [tcp-persist-monitor] section)',
)
@click.option('-H', '--target-host', default='www.nicolacanepa.net', show_default=True, help='Target host to reach')
@click.option('-p', '--target-port', default=443, show_default=True, help='Target TCP port')
@click.option('--path', default='/health', show_default=True, help='HTTP path used as the heartbeat request')
@click.option('-x', '--proxy-host', default=None, help='HTTP CONNECT proxy host (forces the connection over the WAN)')
@click.option('-X', '--proxy-port', default=8080, show_default=True, help='HTTP CONNECT proxy port')
@click.option('--proxy-auth', default=None, help='Proxy Basic auth as user:password')
@click.option(
    '-i', '--heartbeat', default=30, show_default=True, help='Seconds between heartbeats on the open connection'
)
@click.option('-t', '--timeout', default=10, show_default=True, help='Per-request timeout in seconds')
@click.option(
    '--reconnect-delay', default=2, show_default=True, help='Seconds to wait before reconnecting after a drop'
)
@click.option('--pre-script', default=None, help='Shell command to run before (re)connecting, e.g. bring a VPN up')
@click.option(
    '--post-script', default=None, help='Shell command to run after a disconnect/on exit, e.g. tear a VPN down'
)
@click.option('--hook-timeout', default=30, show_default=True, help='Timeout (seconds) for pre/post hook commands')
@click.option(
    '--tls/--no-tls',
    'tls',
    default=True,
    show_default=True,
    help='Use HTTPS (default) or plain HTTP with --no-tls (e.g. port 80)',
)
@click.option('--verify/--no-verify', 'verify_tls', default=True, show_default=True, help='Verify the target TLS cert')
@click.option('--xymon/--no-xymon', default=True, show_default=True, help='Report state transitions to Xymon')
@click.option('--xymon-check', default='wantcp', show_default=True, help='Xymon column name')
@click.option('--xymon-debug', is_flag=True, help='Echo Xymon messages instead of sending them')
@click.option(
    '-l',
    '--log-file',
    default=str(LOG_FILE),
    show_default=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help='Evidence-trail log file',
)
@click.option('-v', '--verbose', is_flag=True, help='Verbose (debug) logging')
@click.option('-q', '--quiet', is_flag=True, help='Quiet (errors only)')
@click.option('-F', '--foreground', is_flag=True, help='Stay attached to the terminal (default: run as daemon)')
@click.option('--kill', is_flag=True, help='Stop the running instance and exit')
def main(
    target_host: str,
    target_port: int,
    path: str,
    proxy_host: str | None,
    proxy_port: int,
    proxy_auth: str | None,
    heartbeat: int,
    timeout: int,
    reconnect_delay: int,
    pre_script: str | None,
    post_script: str | None,
    hook_timeout: int,
    tls: bool,
    verify_tls: bool,
    xymon: bool,
    xymon_check: str,
    xymon_debug: bool,
    log_file: Path,
    verbose: bool,
    quiet: bool,
    foreground: bool,
    kill: bool,
) -> None:
    """Hold a persistent connection to the internet and log every TCP disconnection."""
    if kill:
        kill_running()
        return
    if not foreground:
        daemonize()
        return
    log_path = log_file.expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = get_logger(APP_NAME, verbose, quiet, with_file=str(log_path))
    cfg = MonitorConfig(
        target_host=target_host,
        target_port=int(target_port),
        path=path,
        proxy_host=proxy_host,
        proxy_port=int(proxy_port),
        proxy_auth=proxy_auth,
        heartbeat=int(heartbeat),
        timeout=int(timeout),
        reconnect_delay=int(reconnect_delay),
        pre_script=pre_script,
        post_script=post_script,
        hook_timeout=int(hook_timeout),
        tls=tls,
        verify_tls=verify_tls,
        xymon=xymon,
        xymon_check=xymon_check,
        debug=xymon_debug,
        log=log,
    )
    write_pid_file()
    try:
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    except ValueError:  # not on the main thread (e.g. under a test runner)
        pass
    log.info('Monitoring %s (heartbeat %ss) -> evidence in %s', route_description(cfg), cfg.heartbeat, log_path)
    run_monitor(cfg)


if __name__ == '__main__':
    main()
