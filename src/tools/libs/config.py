"""TOML configuration file, used as defaults below command line options and env vars.

Precedence: command line > environment variables > config file > built-in defaults.

Example (~/.config/<script>/config.toml), for vpn-manager:

    pki-dir = "~/vpn/pki"
    easyrsa = "/usr/share/easy-rsa/easyrsa"

    [xymon]
    warn-days = 45
    crit-days = 10

    [export]
    host = "vpn.example.com"
    proto = "tcp"

Top-level keys apply to the group's own options and to every command; a [command] table
overrides them for that command. Keys are option names, with "-" or "_".
"""

from __future__ import annotations

import logging
import os
import stat
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import typer
except ImportError:
    typer = None  # type: ignore[assignment]

try:
    import click
except ImportError:
    click = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


@dataclass
class ConfigReader:
    """Framework-neutral: reads the TOML file and builds a Click default_map.

    In a group callback, for options declared on the subcommands:
        ctx.default_map = ConfigReader(APP_NAME).load(config_file, commands=ctx.command.commands)
    """

    service_name: str
    # Keys accepted at top level and in [command] sections, mapped to the option's parameter name.
    aliases: Mapping[str, str] = field(default_factory=dict)

    def default_path(self) -> Path:
        base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
        return Path(base) / self.service_name / "config.toml"

    def _normalise(self, section: dict[str, Any]) -> dict[str, Any]:
        out = {}
        for key, value in section.items():
            key = key.replace("-", "_")
            out[self.aliases.get(key, key)] = value
        return out

    def read(self, path: Path | None, commands: Iterable[str]) -> dict[str, Any]:
        """Read and validate the raw TOML data.

        If `path` is None the default location is used and a missing file gives {}.
        """
        explicit = path is not None
        path = (path or self.default_path()).expanduser()
        if not path.is_file():
            if explicit:
                raise ConfigError(f"config file not found: {path}")
            return {}

        try:
            with path.open("rb") as fh:
                data = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"cannot read {path}: {exc}") from None

        has_password = "password" in data or any(isinstance(v, dict) and "password" in v for v in data.values())
        if has_password and path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            log.warning("%s contains a password and is readable by others; run: chmod 600 %s", path, path)

        commands = set(commands)
        unknown = {k for k, v in data.items() if isinstance(v, dict) and k not in commands}
        if unknown:
            raise ConfigError(f"{path}: unknown section(s) {sorted(unknown)}, expected {sorted(commands)}")
        return data

    def top_level(self, data: dict[str, Any]) -> dict[str, Any]:
        """Normalised keys outside any [command] table."""
        return self._normalise({k: v for k, v in data.items() if not isinstance(v, dict)})

    def default_map(self, path: Path | None, commands: Iterable[str]) -> dict[str, Any]:
        """Click default_map: top-level keys (for the group's own options) plus
        {command: {...}} for each subcommand, where a [command] table overrides top-level keys."""
        commands = list(commands)
        data = self.read(path, commands)
        common = self.top_level(data)
        return {**common, **{cmd: {**common, **self._normalise(data.get(cmd, {}))} for cmd in commands}}

    def load(self, path: Path | None, commands: Iterable[str]) -> dict[str, dict[str, Any]]:
        """Per-command part of default_map() only: {command: {param: value}}."""
        commands = list(commands)
        full = self.default_map(path, commands)
        return {cmd: full[cmd] for cmd in commands}

    def apply(self, ctx: Any, value: Path | None) -> None:
        """Load the config into ctx.default_map; works with click and typer contexts."""
        if ctx.resilient_parsing:  # shell completion: don't touch files
            return
        commands = getattr(ctx.command, "commands", {})  # {} for single-command scripts
        ctx.default_map = {**(ctx.default_map or {}), **self.default_map(value, commands)}

    def _help(self) -> str:
        return f"TOML config file. Default: {self.default_path()} (if present)."


class TyperConfigReader(ConfigReader):
    """config_file: Path | None = TyperConfigReader(APP_NAME).option(envvar="X_CONFIG")"""

    def option(self, envvar: str | None = None) -> Any:
        """Default value for an eager `--config` parameter of a typer callback or command."""
        if typer is None:
            raise RuntimeError("TyperConfigReader needs typer installed")

        def callback(ctx: typer.Context, value: Path | None) -> Path | None:
            try:
                self.apply(ctx, value)
            except ConfigError as exc:
                raise typer.BadParameter(str(exc), param_hint="--config") from None
            return value

        return typer.Option(
            None,
            "--config",
            envvar=envvar,
            dir_okay=False,
            is_eager=True,
            callback=callback,
            show_default=False,
            help=self._help(),
        )


class ClickConfigReader(ConfigReader):
    """@ClickConfigReader(APP_NAME).option(envvar="X_CONFIG") on a click group or command."""

    def option(self, envvar: str | None = None) -> Any:
        """Decorator adding an eager `--config` option (not passed to the function)."""
        if click is None:
            raise RuntimeError("ClickConfigReader needs click installed")

        def callback(ctx: click.Context, param: click.Parameter, value: Path | None) -> None:
            try:
                self.apply(ctx, value)
            except ConfigError as exc:
                raise click.BadParameter(str(exc), ctx=ctx, param=param) from None

        return click.option(
            "--config",
            envvar=envvar,
            type=click.Path(dir_okay=False, path_type=Path),
            is_eager=True,
            expose_value=False,
            callback=callback,
            help=self._help(),
        )
