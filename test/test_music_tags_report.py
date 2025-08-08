import pytest

from tools.bin.music_tags_report import Song


@pytest.mark.parametrize(
    "full_path,expected_year,expected_album,expected_artist,expected_n,expected_title",
    (
        ("yaddayadda/artist/1974-album/5 - My Title.mp3", 1974, "album", "artist", 5, "My Title"),
        ("yaddayadda/artist/1974- album/3. My Title, jet-set.mp3", 1974, "album", "artist", 3, "My Title, jet-set"),
        ("yaddayadda/Artist_Name/1974 - album/disc/01-My title è.mp3", 1974, "album", "Artist Name", 1, "My title è"),
    ),
)
def test_song_class(full_path, expected_year, expected_album, expected_artist, expected_n, expected_title):
    song = Song(full_path)
    assert song.year == expected_year
    assert song.album == expected_album
    assert song.artist == expected_artist
    assert song.name == expected_title
    assert song.track == expected_n
