"""TOML configuration file, used as defaults below command line options and env vars.

Precedence: command line > environment variables > config file > built-in defaults.

Example (~/.config/<script>/config.toml):

    host = "192.168.1.50"
    user = "admin"
    password = "secret"
    channel = [0]

    [download]
    output = "~/cctv"
    mp4 = true
"""

from __future__ import annotations

import logging
import os
import stat
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Any, Optional

try:
    import typer
except (ImportError, ValueError):
    typer = None  # type: ignore[assignment]

try:
    import click
except ImportError:  # typer >= 0.27 vends its own click
    click = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


@dataclass
class ConfigReader:
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
        """Read and validate the TOML file; {} if `path` is None and the default file is missing."""
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

    def load(self, path: Path | None, commands: Iterable[str]) -> dict[str, dict[str, Any]]:
        """Return a Click `default_map`: {command: {param: value}}.

        Top-level keys apply to every command; a [command] table overrides them for that command.
        If `path` is None the default location is used and a missing file is not an error.
        """
        data = self.read(path, commands)
        common = self._normalise({k: v for k, v in data.items() if not isinstance(v, dict)})
        return {cmd: {**common, **self._normalise(data.get(cmd, {}))} for cmd in commands}


@dataclass
class TyperConfigReader(ConfigReader):
    """
    In each script:

    from tools.libs.config import ConfigReader

    ConfigFile = ConfigReader(APP_NAME).option(envvar="VPN_CONFIG")


    @app.callback(invoke_without_command=True)
    def main(ctx: typer.Context, config_file: ConfigFile = None, pki_dir: Path = ..., ...):
        ...
    """

    def top_level(self, data: dict[str, Any]) -> dict[str, Any]:
        return self._normalise({k: v for k, v in data.items() if not isinstance(v, dict)})

    def default_map(self, path: Path | None, commands: Iterable[str]) -> dict[str, Any]:
        """Click default_map for a group or a single command: top-level keys for the root
        options, plus {command: {...}} for each subcommand."""
        data = self.read(path, commands)  # the current load() body up to the section check
        common = self.top_level(data)
        per_command = {cmd: {**common, **self._normalise(data.get(cmd, {}))} for cmd in commands}
        return {**common, **per_command}

    def option(self, envvar: str | None = None):
        """Annotated type for a `--config` parameter that loads this config into ctx.default_map."""

        def load(ctx: typer.Context, value: Path | None) -> Path | None:
            if ctx.resilient_parsing:  # shell completion: don't touch files
                return value
            commands = getattr(ctx.command, "commands", {})  # {} for single-command scripts
            try:
                ctx.default_map = {**(ctx.default_map or {}), **self.default_map(value, commands)}
            except ConfigError as exc:
                raise typer.BadParameter(str(exc), param_hint="--config") from None
            return value

        return Annotated[
            Optional[Path],
            typer.Option(
                "--config",
                envvar=envvar,
                dir_okay=False,
                is_eager=True,
                callback=load,
                show_default=False,
                help=f"TOML config file. Default: {self.default_path()} (if present).",
            ),
        ]


class AutoConfigReader(ConfigReader):
    """
    Using it in a Click script:

    config = ConfigReader("my-tool")

    @click.group()
    @config.click_option(envvar="MY_TOOL_CONFIG")
    @click.option("--pki-dir", type=click.Path(path_type=Path), default="pki")
    def cli(pki_dir): ...
    """

    def apply(self, ctx, value: Path | None) -> None:
        """Load the config into ctx.default_map (works with click and typer contexts)."""
        if ctx.resilient_parsing:  # shell completion
            return
        commands = getattr(ctx.command, "commands", {})
        ctx.default_map = {**(ctx.default_map or {}), **self.default_map(value, commands)}

    def _help(self) -> str:
        return f"TOML config file. Default: {self.default_path()} (if present)."

    def typer_option(self, envvar: str | None = None):
        import typer

        def callback(ctx: typer.Context, value: Path | None) -> Path | None:
            try:
                self.apply(ctx, value)
            except ConfigError as exc:
                raise typer.BadParameter(str(exc), param_hint="--config") from None
            return value

        return Annotated[
            Optional[Path],
            typer.Option("--config", envvar=envvar, dir_okay=False, is_eager=True,
                         callback=callback, show_default=False, help=self._help()),
        ]

    def click_option(self, envvar: str | None = None):
        import click

        def callback(ctx: click.Context, param: click.Parameter, value: Path | None) -> None:
            try:
                self.apply(ctx, value)
            except ConfigError as exc:
                raise click.BadParameter(str(exc), ctx=ctx, param=param) from None

        return click.option(
            "--config", envvar=envvar, type=click.Path(dir_okay=False, path_type=Path),
            is_eager=True, expose_value=False, callback=callback, help=self._help(),
        )
