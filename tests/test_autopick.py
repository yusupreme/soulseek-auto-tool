from rich.console import Console

from soulseek_auto_tool.autopick import auto_pick, auto_select
from soulseek_auto_tool.choose import choose_matches
from soulseek_auto_tool.state import Session
from test_choose import _match, _scripted, _session, _track


def _console():
    return Console(record=True, width=120, force_terminal=False)


def _t(matches, query="Artist Song", duration=300, raw_title="Artist - Song"):
    return _track("1", query, matches, duration=duration, raw_title=raw_title)


def test_picks_the_largest_file_with_the_right_name_and_length():
    big_wrong_length = _match("a", "Artist - Song.mp3", length=480, size=20_000_000)
    right = _match("b", "Artist - Song.mp3", length=301, size=12_000_000)
    smaller = _match("c", "Artist - Song.mp3", length=300, size=9_000_000)
    assert auto_pick(_t([big_wrong_length, right, smaller])) is right


def test_length_outside_tolerance_is_left_to_the_user():
    assert auto_pick(_t([_match("a", "Artist - Song.mp3", length=306)])) is None
    assert auto_pick(_t([_match("a", "Artist - Song.mp3", length=306)]), tolerance=10) is not None


def test_unknown_length_is_never_auto_picked():
    assert auto_pick(_t([_match("a", "Artist - Song.mp3", length=None)])) is None
    assert auto_pick(_t([_match("a", "Artist - Song.mp3")], duration=None)) is None


def test_snippets_are_never_auto_picked():
    track = _t([_match("a", "Artist - Song.mp3", length=60)], duration=60, raw_title="Artist - Song SNIPPET")
    assert auto_pick(track) is None


def test_every_search_word_must_be_in_the_file_name():
    # 2 of 3 words is enough for a search hit, not for an unattended pick
    track = _t([_match("a", "Artist - Other.mp3")], query="Artist Song Extra")
    assert auto_pick(track) is None


def test_a_version_the_soundcloud_title_does_not_have_is_not_auto_picked():
    remix = _match("a", "Artist - Song (Other Remix).mp3", size=20_000_000)
    plain = _match("b", "Artist - Song.mp3", size=10_000_000)
    assert auto_pick(_t([remix, plain])) is plain
    assert auto_pick(_t([remix])) is None


def test_a_version_named_in_the_soundcloud_title_is_fine():
    track = _t([_match("a", "Artist - Song (Dub Mix).mp3")], query="Artist Song", raw_title="Artist - Song (Dub Mix)")
    assert auto_pick(track) is not None


def test_auto_select_marks_tracks_and_leaves_the_rest(tmp_path):
    sure = _t([_match("a", "Artist - Song.mp3")])
    unsure = _track("2", "Artist Song", [_match("b", "Artist - Song.mp3", length=450)], raw_title="Artist - Song")
    empty = _track("3", "Nothing", [])
    session = _session(tmp_path, [sure, unsure, empty])
    console = _console()

    assert auto_select(session, console) == 1
    assert (sure.download_status, sure.picked_by, sure.chosen["username"]) == ("chosen", "auto", "a")
    assert unsure.download_status == "" and empty.download_status == ""
    text = console.export_text()
    assert "Auto-selected 1" in text and "1 with matches need your decision" in text
    assert Session.load(session.path).tracks[0].picked_by == "auto"


def test_decided_and_failed_tracks_are_not_auto_selected_again(tmp_path):
    skipped, failed = _t([_match("a", "Artist - Song.mp3")]), _t([_match("a", "Artist - Song.mp3")])
    skipped.download_status, failed.download_status = "skipped", "failed"
    assert auto_select(_session(tmp_path, [skipped, failed]), _console()) == 0


def test_remaining_tracks_are_still_reviewed_by_hand(tmp_path):
    sure = _t([_match("a", "Artist - Song.mp3")])
    unsure = _track("2", "Artist Song", [_match("b", "Artist - Song.mp3", length=450)], raw_title="Artist - Song")
    session = _session(tmp_path, [sure, unsure])
    auto_select(session, _console())
    assert choose_matches(session, _console(), _scripted([""])) is True  # only one prompt: the unsure track
    assert (unsure.picked_by, unsure.chosen["username"]) == ("user", "b")
