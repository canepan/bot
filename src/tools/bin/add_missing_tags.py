#!/mnt/opt/nicola/tools/bin/python
import fileinput
import os
import re
import shlex

import click
import yaml


def process(curr_file: str, text: list, overwrite: bool, verbose: bool) -> None:
    if text:
        if verbose:
            print(f"Processing {curr_file}")
        data = yaml.safe_load("\n".join(text))
        album_title_with_year = os.path.basename(os.path.dirname(curr_file))
        suffix = ""
        if re.match("(dis[ck]|cd) *[0-9]+$", album_title_with_year, re.I):
            suffix = f"-{album_title_with_year}"
            album_title_with_year = os.path.basename(os.path.dirname(os.path.dirname(curr_file)))
        if re.match("[0-9]{4}", album_title_with_year):
            album_title = album_title_with_year[4:].lstrip(" -")
            year = int(album_title_with_year[:4])
        else:
            album_title = album_title_with_year
            year = None
        if re.search(" *@[0-9]+$", album_title):
            album_title = re.sub(" *@[0-9]+$", "", album_title).rstrip(" ")
        album_title = f"{album_title}{suffix}"
        existing_tags = {}
        for k, v in [(l, m) for i in data for l, m in i.items()]:
            existing_tags[k] = v
            if not overwrite and k == "album":
                if verbose and album_title:
                    click.echo(f"Keeping {k} as {v} instead of changing to {album_title}")
                album_title = v
        extra = ""
        if year and not existing_tags.get("year"):
            extra = f"{extra} set:year={year}"
        if (artist := existing_tags.get("artist")) and album_title.startswith(artist):
            album_title = album_title[len(artist):].lstrip(" -")
        if album_title != existing_tags.get("album"):
            extra = f"{extra} set:{click.style('album', fg='green')}={shlex.quote(album_title)}"
        if extra:
            return f"tagutil{extra} {shlex.quote(curr_file)}"


@click.command(context_settings={"allow_extra_args": True})
@click.option("--overwrite", "-O", is_flag=True, default=False)
@click.option("--verbose", "-v", is_flag=True, default=False)
@click.pass_context
def main(ctx: click.core.Context, overwrite: bool, verbose: bool):
    curr_file = None
    text = []
    commands = []
    for line in fileinput.input(ctx.args):
        if line.startswith("# "):
            commands.append(process(curr_file, text, overwrite=overwrite, verbose=verbose))
            text = []
            curr_file = os.path.abspath(line[2:]).rstrip()
        text.append(line)
    commands.append(process(curr_file, text, overwrite=overwrite, verbose=verbose))
    if verbose:
        extra_space = "  "
        click.echo("Run:  ")
    else:
        extra_space = ""
    all_commands = f"\n{extra_space}".join(c for c in commands if c)
    click.echo(f"{extra_space}{all_commands}")


if __name__ == "__main__":
    main()
