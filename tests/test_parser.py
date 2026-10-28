import pytest

from soulseek_auto_tool.models import Track
from soulseek_auto_tool.parser import (
    apply_regex_parse,
    build_query,
    clean_title,
    parse_tracks,
    parse_title,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Artist - Track [FREE DL]", "Artist - Track"),
        ("Artist - Track (Free Download) 🔥", "Artist - Track"),
        ("Artist - Track (Club Remix)", "Artist - Track (Club Remix)"),
        ("Artist - Track [Premiere]", "Artist - Track"),
        ("  Artist - Track   OUT NOW  ", "Artist - Track"),
        ("Cari Lekebusch - Rockcarver.aiff", "Cari Lekebusch - Rockcarver"),
        ("Artist - Track.WAV", "Artist - Track"),
        ("B2. Blame The Mono - Funfair  SNIPPET", "Blame The Mono - Funfair"),
        ("Setaoc Mass - Silent Tension - SNIPPET", "Setaoc Mass - Silent Tension"),
        ("A1 Passed Out on the Sofa", "Passed Out on the Sofa"),
    ],
)
def test_clean_title(raw, expected):
    assert clean_title(raw) == expected


def test_parse_title_with_separator():
    parsed = parse_title("Daft Punk - One More Time [FREE DL]", "Some Uploader")
    assert (parsed.artist, parsed.title) == ("Daft Punk", "One More Time")
    assert parsed.confidence >= 0.7


def test_parse_title_without_separator_uses_uploader_with_low_confidence():
    parsed = parse_title("Late Night Groove", "DJ Foo")
    assert (parsed.artist, parsed.title) == ("DJ Foo", "Late Night Groove")
    assert parsed.confidence < 0.7


def test_hyphen_inside_a_word_is_not_a_separator():
    parsed = parse_title("Jay-Z - Song", "x")
    assert (parsed.artist, parsed.title) == ("Jay-Z", "Song")


def test_build_query_strips_punctuation_that_breaks_soulseek_search():
    assert build_query("Artist", "-Track (Remix) [x]") == "Artist Track Remix x"
    assert build_query("Beyoncé", "Don’t Stop") == "Beyoncé Don't Stop"


def test_apply_regex_parse_sets_query():
    tracks = [Track(id="1", raw_title="A - B", uploader="u")]
    apply_regex_parse(tracks)
    assert tracks[0].query == "A B"


def test_parse_tracks_without_key_uses_regex():
    tracks = [Track(id="1", raw_title="A - B", uploader="u")]
    assert parse_tracks(tracks, api_key="").startswith("regex")
    assert tracks[0].query == "A B"


def test_parse_tracks_falls_back_to_regex_when_ai_fails(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("soulseek_auto_tool.parser.ai_parse", boom)
    tracks = [Track(id="1", raw_title="A - B", uploader="u")]
    assert "failed" in parse_tracks(tracks, api_key="fake")
    assert tracks[0].query == "A B"
