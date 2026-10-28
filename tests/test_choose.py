from rich.console import Console

from soulseek_auto_tool.choose import (
    choose_matches,
    fmt_time,
    is_snippet,
    length_difference,
    render_card,
)
from soulseek_auto_tool.models import Track
from soulseek_auto_tool.state import Session


def _match(user, name, length=300, size=10_000_000, **extra):
    return {"username": user, "filename": rf"music\{name}", "size": size, "extension": "mp3",
            "bitrate": 320, "length": length, "free_slot": True, "queue_length": 0, **extra}


def _track(id, query, matches, duration=300, raw_title=None):
    return Track(id=id, raw_title=raw_title or query, uploader="up", query=query, searched=True,
                 matches=matches, duration=duration, url=f"https://soundcloud.com/x/{id}")


def _session(tmp_path, tracks):
    return Session(path=tmp_path / "s.json", playlist_url="u", playlist_name="Mix", tracks=tracks)


def _scripted(answers):
    it = iter(answers)
    return lambda prompt: next(it)


def _console():
    return Console(record=True, width=120, force_terminal=False)


def test_fmt_time():
    assert fmt_time(None) == "?:??"
    assert fmt_time(372) == "6:12"
    assert fmt_time(59.6) == "1:00"
    assert fmt_time(3725) == "1:02:05"


def test_length_difference_text_and_colors():
    assert length_difference(300, 302) == ("+0:02", "green")
    assert length_difference(300, 297) == ("-0:03", "green")
    assert length_difference(300, 308) == ("+0:08", "yellow")
    assert length_difference(300, 521) == ("+3:41", "red")
    assert length_difference(None, 300) == ("", "dim")


def test_is_snippet():
    assert is_snippet(_track("1", "q", [], raw_title="Traum SNIPPET"))
    assert is_snippet(_track("1", "q", [], raw_title="Tethys (Preview)"))
    assert not is_snippet(_track("1", "q", [], raw_title="Tethys"))


def test_card_shows_soundcloud_and_soulseek_lengths_side_by_side():
    track = _track("1", "Artist Song", [_match("peer", "Artist - Song.mp3", length=312)], duration=300)
    console = _console()
    render_card(track, 1, 1, 0, console)
    text = console.export_text()
    assert "5:00" in text and "5:12" in text and "+0:12" in text
    assert "Artist - Song.mp3" in text and "peer" in text and "soundcloud.com/x/1" in text


def test_card_does_not_crash_on_square_brackets_in_names():
    track = _track("1", "q", [_match("[bold]peer", "[Phase] [free dl] Song.mp3")], raw_title="[red]Song[/red] [x]")
    console = _console()
    render_card(track, 1, 1, 0, console)
    assert "[Phase] [free dl] Song.mp3" in console.export_text()


def test_snippet_card_explains_longer_file():
    track = _track("1", "q", [_match("peer", "Song.mp3", length=420)], duration=60, raw_title="Song SNIPPET")
    console = _console()
    render_card(track, 1, 1, 0, console)
    assert "snippet" in console.export_text().lower()


def test_card_without_matches_says_so():
    console = _console()
    render_card(_track("1", "q", []), 1, 1, 0, console)
    assert "No 320 kbps MP3 matches" in console.export_text()


def test_enter_takes_first_number_picks_other_s_skips_q_quits(tmp_path):
    two = [_match("a", "1.mp3"), _match("b", "1b.mp3")]
    session = _session(tmp_path, [_track("1", "one", two), _track("2", "two", two),
                                  _track("3", "three", two), _track("4", "four", two)])
    assert choose_matches(session, _console(), _scripted(["", "2", "s", "q"])) is False
    t = session.tracks
    assert (t[0].download_status, t[0].chosen["username"]) == ("chosen", "a")
    assert (t[1].download_status, t[1].chosen["username"]) == ("chosen", "b")
    assert t[2].download_status == "skipped"
    assert t[3].download_status == ""  # asked again on the next run
    assert Session.load(session.path).tracks[2].download_status == "skipped"


def test_more_results_pages_through_and_numbers_continue(tmp_path):
    matches = [_match(f"u{i}", f"{i}.mp3") for i in range(12)]
    session = _session(tmp_path, [_track("1", "one", matches)])
    assert choose_matches(session, _console(), _scripted(["m", "m", "11"])) is True
    assert session.tracks[0].chosen["username"] == "u10"


def test_invalid_input_reprompts_instead_of_choosing(tmp_path):
    session = _session(tmp_path, [_track("1", "one", [_match("a", "1.mp3")])])
    choose_matches(session, _console(), _scripted(["99", "huh", "1"]))
    assert session.tracks[0].chosen["username"] == "a"


def test_edit_search_retries_and_then_user_picks_new_result(tmp_path):
    track = _track("1", "wrong words", [])
    session = _session(tmp_path, [track])
    seen = []

    def retry(t):
        seen.append(t.query)
        t.matches = [_match("fresh", "found.mp3")]

    assert choose_matches(session, _console(), _scripted(["e", "Real Artist - Real Title!", ""]), retry=retry)
    assert seen == ["Real Artist Real Title"]
    assert track.chosen["username"] == "fresh" and track.query == "Real Artist Real Title"


def test_enter_does_nothing_when_there_are_no_matches(tmp_path):
    track = _track("1", "none", [])
    session = _session(tmp_path, [track])
    choose_matches(session, _console(), _scripted(["", "s"]))
    assert track.chosen is None and track.download_status == "skipped"


def test_decided_tracks_are_not_asked_again(tmp_path):
    done = _track("1", "one", [_match("a", "1.mp3")])
    done.download_status = "skipped"
    session = _session(tmp_path, [done])
    assert choose_matches(session, _console(), _scripted([])) is True
