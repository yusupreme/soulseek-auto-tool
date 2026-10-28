import httpx
import pytest
from rich.console import Console

from soulseek_auto_tool.models import Track
from soulseek_auto_tool.pacer import Pacer
from soulseek_auto_tool.report import write_log
from soulseek_auto_tool.review import review_tracks
from soulseek_auto_tool.search import run_searches
from soulseek_auto_tool.slskd import SlskdClient, SlskdError
from soulseek_auto_tool.state import Session


def _session(tmp_path, count=3):
    tracks = [
        Track(id=str(i), raw_title=f"Artist - Song {i}", uploader="u", artist="Artist",
              title=f"Song {i}", confidence=0.8, query=f"Artist Song {i}")
        for i in range(count)
    ]
    return Session(path=tmp_path / "s.json", playlist_url="http://x", playlist_name="Mix", tracks=tracks)


def _scripted(answers):
    it = iter(answers)
    return lambda prompt: next(it)


QUIET = Console(quiet=True)


def test_review_accept_edit_skip(tmp_path):
    session = _session(tmp_path)
    done = review_tracks(session, QUIET, _scripted(["", "Other Name - Edited", "s"]))
    assert done
    assert [t.status for t in session.tracks] == ["accepted", "accepted", "skipped"]
    assert session.tracks[1].query == "Other Name Edited"


def test_review_quit_saves_and_resume_continues(tmp_path):
    session = _session(tmp_path)
    assert review_tracks(session, QUIET, _scripted(["", "q"])) is False
    reloaded = Session.load(session.path)
    assert [t.status for t in reloaded.tracks] == ["accepted", "pending", "pending"]
    assert review_tracks(reloaded, QUIET, _scripted(["a"])) is True
    assert all(t.status == "accepted" for t in reloaded.tracks[1:])


def _slskd_transport(log):
    def handler(request: httpx.Request) -> httpx.Response:
        log.append((request.method, request.url.path))
        path = request.url.path
        if request.method == "POST" and path == "/api/v0/searches":
            return httpx.Response(200, json={"id": "ignored"})
        if request.method == "GET" and path.endswith("/responses"):
            return httpx.Response(200, json=[{
                "username": "peer", "hasFreeUploadSlot": True, "queueLength": 0, "uploadSpeed": 1_000_000,
                "files": [{"filename": r"m\Artist - Song 0.mp3", "size": 1000, "bitRate": 320}],
            }])
        if request.method == "GET" and path.startswith("/api/v0/searches/"):
            return httpx.Response(200, json={"state": "Completed, ResponseLimitReached"})
        if request.method == "GET" and path == "/api/v0/application":
            return httpx.Response(200, json={})
        return httpx.Response(204)

    return httpx.MockTransport(handler)


def test_run_searches_paces_ranks_saves_and_reports(tmp_path):
    session = _session(tmp_path, count=2)
    for t in session.tracks:
        t.status = "accepted"
    session.tracks[1].artist, session.tracks[1].title = "Totally", "Unrelated Words"
    session.tracks[1].query = "Totally Unrelated Words"
    log, slept = [], []
    client = SlskdClient("http://slskd", "key", transport=_slskd_transport(log), sleep=lambda s: None)
    now = [0.0]
    pacer = Pacer(3, 4, sleep=lambda s: (slept.append(s), now.__setitem__(0, now[0] + s)),
                  clock=lambda: now[0], uniform=lambda a, b: 3.5)

    run_searches(session, client, pacer)

    assert slept == [3.5]  # one gap between two searches
    assert sum(1 for m, p in log if m == "POST") == 2
    assert session.tracks[0].searched and session.tracks[0].matches[0]["username"] == "peer"
    assert session.tracks[1].matches == []  # peer's file doesn't match this query

    text = write_log(session, tmp_path / "out").read_text()
    assert "## Found but not decided yet" in text and "## Not found" in text
    assert "Totally Unrelated Words" in text
    assert session.tracks[1].search_stats["peers"] == 1  # recorded, to explain the miss later


def test_searched_tracks_are_not_searched_again(tmp_path):
    session = _session(tmp_path, count=1)
    session.tracks[0].status, session.tracks[0].searched = "accepted", True
    log = []
    client = SlskdClient("http://slskd", "key", transport=_slskd_transport(log))
    run_searches(session, client, Pacer(0, 0))
    assert log == []


def test_bad_api_key_gives_a_clear_error():
    transport = httpx.MockTransport(lambda r: httpx.Response(401))
    client = SlskdClient("http://slskd", "wrong", transport=transport)
    with pytest.raises(SlskdError, match="API key"):
        client.check()


def test_track_with_no_matches_is_retried_without_remix_words(tmp_path):
    track = Track(id="1", raw_title="x", uploader="u", artist="Artist", title="Song 0 (Some Remix)",
                  query="Artist Song 0 Some Remix", status="accepted")
    session = Session(path=tmp_path / "s.json", playlist_url="u", playlist_name="Mix", tracks=[track])
    log, retried = [], []
    client = SlskdClient("http://slskd", "key", transport=_slskd_transport(log), sleep=lambda s: None)

    run_searches(session, client, Pacer(0, 0), on_fallback=lambda old, new: retried.append((old, new)))

    assert retried == [("Artist Song 0 Some Remix", "Artist Song 0")]
    assert track.query == "Artist Song 0" and track.matches[0]["username"] == "peer"
    assert sum(1 for m, p in log if m == "POST") == 2  # original search + one retry


def test_reset_empty_only_touches_tracks_that_found_nothing(tmp_path):
    session = _session(tmp_path, count=4)
    empty, skipped_empty, has_matches, downloaded = session.tracks
    for t in session.tracks:
        t.searched = True
    skipped_empty.download_status = "skipped"
    has_matches.matches = [{"username": "peer"}]
    downloaded.download_status, downloaded.chosen = "done", {"username": "peer"}

    assert session.reset_empty() == 2
    assert not empty.searched and not skipped_empty.searched and skipped_empty.download_status == ""
    assert has_matches.searched and downloaded.download_status == "done"
    assert Session.load(session.path).tracks[0].searched is False
