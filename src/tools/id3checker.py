import json
import os
from collections import defaultdict

import click
import eyed3

def neutralize(text: str) -> str:
    return text.lower().replace("_", " ").replace(".", " ").replace("'", "")

@click.command()
@click.argument("base_dir")
@click.option("--per-artist", "-a", is_flag=True)
@click.option("--verbose", "-v", is_flag=True)
def main(base_dir: str, per_artist: bool, verbose: bool):
    tags = defaultdict(lambda :defaultdict(list))
    broken_files = list()
    for dirpath, dirnames, filenames in os.walk(base_dir):
        for filename in sorted(filenames):
            curr_file = eyed3.load(os.path.join(dirpath, filename))
            if curr_file and curr_file.tag:
                album = curr_file.tag.album or dirpath
                artist = curr_file.tag.album_artist or curr_file.tag.artist
                text = curr_file.tag.title or filename
                num = f"{curr_file.tag.track_num[0]}/{curr_file.tag.track_num[1]}"
                if verbose:
                    if album != dirpath:
                        album = f"{album} ({dirpath})"
                    if text != filename:
                        text = f"{text} ({filename})"
                if per_artist:
                    tags[artist][album].append(f"{num} {text}")
                else:
                    tags[album][artist].append(f"{num} {text}")
                if neutralize(curr_file.tag.title) not in neutralize(curr_file.path) or not curr_file.tag.album or not artist:
                    broken_files.append(curr_file)
    click.echo(json.dumps(tags, indent=2, ensure_ascii=False))
    if broken_files:
        click.echo("Broken:")
    for broken in broken_files:
        click.echo(f"{broken.path} - {broken.tag.title} ({broken.tag.album_artist or broken.tag.artist}, {broken.tag.album})")


if __name__ == "__main__":
    main()
