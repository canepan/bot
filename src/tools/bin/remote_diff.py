#!/mnt/opt/nicola/tools/bin/python
import os
import re
from difflib import unified_diff
from subprocess import check_output

import click

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


def cat_cmd(pathspec: str, file_name: str) -> list:
    try:
        return ["ssh", pathspec.split(":")[0], "cat", os.path.join(pathspec.split(":")[1], file_name)]
    except Exception:
        return ["cat", os.path.join(pathspec, file_name)]


@click.command()
@click.argument("source")
@click.argument("destination")
@click.option("--verbose/--quiet", "-v/-q", default=None)
def main(source: str, destination: str, verbose: bool):
    output = check_output(["rsync", "-rtni", source, destination], universal_newlines=True)
    if matches := re.findall("(^([<>c*].c|[<>c*]..s)|(\+\+\+)).*\s([\w/.]+)$", output, re.M):
        click.echo(output)
        click.echo(HELP)
        if verbose:
            for match in matches:
                s_content = check_output(cat_cmd(source, match[3]), universal_newlines=True)
                d_content = check_output(cat_cmd(destination, match[3]), universal_newlines=True)
                for diff_line in unified_diff(s_content.splitlines(), d_content.splitlines(), os.path.join(source, match[3]), os.path.join(destination, match[3])):
                    click.echo(diff_line)


if __name__ == "__main__":
    main()
