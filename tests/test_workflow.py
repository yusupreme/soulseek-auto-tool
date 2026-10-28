import httpx
import pytest
from rich.console import Console

from soulseek_auto_tool.models import Track
from soulseek_auto_tool.pacer import Pacer
from soulseek_auto_tool.report import write_report
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

    md, js = write_report(session, tmp_path / "out")
    assert "peer" in md.read_text() and "No matches found." in md.read_text()
    assert js.exists()


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
