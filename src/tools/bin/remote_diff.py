#!/usr/bin/env python3
"""Show the diff of files rsync would transfer, between local and/or remote dirs.

`source` and `destination` are rsync-style pathspecs: `host:/path` for a
remote side (read over SFTP via paramiko), plain `/path` for a local side.
"""

import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from difflib import unified_diff
from subprocess import check_output

import click
import paramiko

HELP = """
Legend: each line in the format
YXcstpoguax FILENAME
 Y: '
  o < file to be transferred to remote (sent).
  o > file to be transferred to local (received).
  o c local change/creation for the item (create a dir, change a symlink, etc.).
  o h hard link to another item (requires --hard-links).
  o . not being updated (though it might have attributes that are being modified).
  o * the rest of the itemized-output area contains a message (e.g. "deleting").
  o + new file
 X: f - file, d - dir, L - symlink, D - device, S - special file
 Checksum, Size, Time, Perms, Owner, Group, U?, Acl, eXtended attrs
"""


@dataclass
class PathSpec:
    """An rsync-style pathspec, parsed into host (None for local) and path."""

    host: str | None
    path: str

    @classmethod
    def parse(cls, spec: str) -> 'PathSpec':
        """'host:/path' -> PathSpec('host', '/path'); '/path' -> PathSpec(None, '/path').

        >>> PathSpec.parse('nas:/srv/etc')
        PathSpec(host='nas', path='/srv/etc')
        >>> PathSpec.parse('/etc')
        PathSpec(host=None, path='/etc')
        """
        host, sep, path = spec.partition(':')
        if sep and not spec.startswith('/') and '/' not in host:
            return cls(host=host, path=path or '.')
        return cls(host=None, path=spec)

    def label(self, fname: str) -> str:
        prefix = f'{self.host}:' if self.host else ''
        return f'{prefix}{os.path.join(self.path, fname)}'


@contextmanager
def sftp_client(host: str):
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.WarningPolicy())
    client.connect(host)
    try:
        yield client.open_sftp()
    finally:
        client.close()


def read_file(spec: PathSpec, fname: str) -> str:
    """Read `fname` under spec.path; over SFTP for remote specs, locally otherwise."""
    full = os.path.join(spec.path, fname)
    if spec.host is None:
        with open(full) as fh:
            return fh.read()
    with sftp_client(spec.host) as sftp:
        with sftp.open(full, 'r') as fh:
            return fh.read().decode()


def iter_diffs(source: PathSpec, destination: PathSpec, matches: list[tuple[str, str, str]]):
    for _line, change, fname in matches:
        s_content = d_content = None
        if "+++" in change:
            if change[0] == "<":
                d_content = " "
            if change[0] == ">":
                s_content = " "
        s_content = s_content if s_content is not None else read_file(source, fname)
        d_content = d_content if d_content is not None else read_file(destination, fname)
        yield from unified_diff(
            s_content.splitlines(),
            d_content.splitlines(),
            source.label(fname),
            destination.label(fname),
        )


@click.command()
@click.argument("source")
@click.argument("destination")
@click.option("--verbose/--quiet", "-v/-q", default=None)
def main(source: str, destination: str, verbose: bool):
    output = check_output(["rsync", "-rtni", source, destination], universal_newlines=True)
    if matches := re.findall(r"(^([<>c*].c|[<>c*]..s|.f\+\+\+)).*\s([\w/.]+)$", output, re.M):
        click.echo(output)
        click.echo(HELP)
        if verbose:
            src, dst = PathSpec.parse(source), PathSpec.parse(destination)
            for diff_line in iter_diffs(src, dst, matches):
                click.echo(diff_line)


if __name__ == "__main__":
    main()
