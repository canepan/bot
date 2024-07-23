import json
import os
from collections import defaultdict

import click
import eyed3


@click.command()
@click.argument("base_dir")
def main(base_dir: str):
    tags = defaultdict(list)
    for dirpath, dirnames, filenames in os.walk(base_dir):
        for filename in filenames:
            curr_file = eyed3.load(os.path.join(dirpath, filename))
            if curr_file and curr_file.tag:
                text = f"{curr_file.tag.album_artist or curr_file.tag.artist} - {curr_file.tag.album} - {curr_file.tag.title}"
                click.echo(text)
                tags[curr_file.tag.album_artist or curr_file.tag.artist].append(text)
    click.echo(json.dumps(tags, indent=2))


if __name__ == "__main__":
    main()
