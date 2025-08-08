#!/mnt/opt/nicola/tools/bin/python3
import glob
import os
import re
import shlex
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from itertools import chain

import click
import eyed3


def find_mp3s(top: str = ".") -> list:
    for f in glob.iglob(f"{top}/**/*.mp3", recursive=True):
        yield f


def arg_for(k, i) -> str:
    if i == "album":
        return k.split("/")[-2].split("-", maxsplit=1)[1]
    if i == "artist":
        return k.split("/")[-3]
    if i == "title":
        return re.sub("^[0-9]+([^0-9 ])* (- )?", "", k.split("/")[-1][:-4])
    if i == "track":
        return re.sub("[^0-9].*$", "", k.split("/")[-1])
    if i == "year":
        return k.split("/")[-2].split("-", maxsplit=1)[0]
    return ""


def quote(text: str) -> str:
    return shlex.quote(text)

def param_for(k, i) -> str:
    return f'{i.replace("_", "-")} {quote(arg_for(os.path.abspath(k.tag.file_info.name), i))}'


@dataclass
class Song:
    path: str

    def __post_init__(self):
        self.indexes = {"album": -2, "title": -1, "artist": -3}
        norm_path = "_".join(filter(None, re.split("[-_\s]", self.path)))
        try:
            self._year, self._album = norm_path.split("/")[self.indexes["album"]].split("_", maxsplit=1)
        except Exception as e:
            # There could be "CDx" sub-dir
            try:
                self.indexes["album"] -= 1
                self.indexes["artist"] -= 1
                self._year, self._album = norm_path.split("/")[self.indexes["album"]].split("_", maxsplit=1)
            except Exception as e_sub:
                click.echo(f"Error splitting {self.path} for album/year: {e}; {e_sub}")
        self._album = self._album.replace("_", " ")
        try:
            # self._name = re.sub("^[0-9]+([^0-9 ])* (- )?", "", norm_path.split("/")[self.indexes["title"]][:-4]).replace("_", " ")
            self._name = re.sub("^[0-9]+[-_.\s]*", "", self.path.split("/")[self.indexes["title"]][:-4]).replace("_", " ")
        except Exception as e:
            click.echo(f"Error searching name from {self.path}: {e}")
        try:
            self._track = re.sub("[^0-9].*$", "", norm_path.split("/")[self.indexes["title"]])
        except Exception as e:
            click.echo(f"Error searching track from {self.path}: {e}")
        try:
            self._artist = norm_path.split("/")[self.indexes["artist"]].replace("_", " ")
        except Exception as e:
            click.echo(f"Error splitting {self.path} for artist: {e}")

    @property
    def album(self) -> str:
        return self._album

    @property
    def artist(self) -> str:
        return self._artist

    @property
    def name(self) -> str:
        return self._name

    @property
    def track(self) -> int:
        return int(self._track or "0")

    @property
    def year(self) -> int:
        return int(self._year)


def comparable(text_or_int, exact):
    if not (exact and isinstance(text_or_int, int)):
        text_or_int = unicodedata.normalize("NFKD", text_or_int.casefold().replace("'", ""))
        text_or_int = "".join([c for c in text_or_int if not unicodedata.combining(c)])
    return text_or_int


@click.command()
@click.argument("sources", nargs=-1)
def main(sources: list):
    incomplete = defaultdict(list)
    mp3s = chain()
    count = 0
    differences = 0
    for source in sources or ["."]:
        if os.path.isdir(source):
            mp3s = chain(mp3s, find_mp3s(source))
        else:
            mp3s = chain(mp3s, [source])
    for mp3 in mp3s:
        count += 1
        # 'album_artist', 'album_type', 'artist', 'artist_origin', 'artist_url', 'audio_file_url', 'audio_source_url',
        # 'best_release_date', 'bpm', 'cd_id', 'chapters', 'clear', 'comments', 'commercial_url', 'composer',
        # 'copyright', 'copyright_url', 'disc_num', 'encoded_by', 'encoding_date', 'extended_header', 'file_info',
        # 'frame_set', 'frameiter', 'genre', 'getBestDate', 'getTextFrame', 'header', 'images', 'internet_radio_url',
        # 'isV1', 'isV2', 'lyrics', 'non_std_genre', 'objects', 'original_artist', 'original_release_date', 'parse',
        # 'payment_url', 'play_count', 'popularities', 'privates', 'publisher', 'publisher_url', 'read_only',
        # 'recording_date', 'release_date', 'remove', 'save', 'setTextFrame', 'table_of_contents', 'tagging_date',
        # 'terms_of_use', 'title', 'track_num', 'unique_file_ids', 'unknown_frame_ids', 'user_text_frames',
        # 'user_url_frames', 'version'
        try:
            audiofile = eyed3.load(mp3)
            song = Song(os.path.abspath(mp3))
            tags_expected = (
                (audiofile.tag.artist, song.artist, "artist", True),
                (audiofile.tag.album, song.album.casefold(), "album", False),
                (audiofile.tag.title, song.name.casefold(), "name", False),
                (audiofile.tag.track_num.count, song.track, "track", True),
                ((audiofile.tag.release_date or audiofile.tag.recording_date).year, song.year, "year", True),
            )
            for tag, expected, name, exact in tags_expected:
                if tag:
                    if not comparable(expected, exact) == comparable(tag, exact):
                        click.echo(f"{mp3} - {name} {tag!r} != {expected!r}")
                        differences += 1
                else:
                    incomplete[audiofile].append(name)
        except OSError as e:
            click.echo(f"Error {e!r} for {mp3} (check your input)")
            raise e
        except Exception as e:
            click.echo(f"Error {e!r} for {mp3}")
            incomplete[audiofile].append(str(e))
    commands = []
    for k, v in incomplete.items():
        if k.tag:
            click.echo(f"{k.tag.file_info.name}: {v}")
        else:
            click.echo(f"{k._path} missing tag")
        if v and isinstance(v[0], str):
            commands.append(f"eyeD3 --{' --'.join([param_for(k, i) for i in v if isinstance(i, str)])} {quote(k.tag.file_info.name)}")
    click.echo("\n".join(commands))
    click.echo(f"Checked {count} files, {len(incomplete)} missing data, {differences} discrepancies")

if __name__ == "__main__":
    main()
