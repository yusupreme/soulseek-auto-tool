import httpx

from soulseek_auto_tool.download import playlist_folder_name, run_downloads
from soulseek_auto_tool.models import Track
from soulseek_auto_tool.slskd import SlskdClient
from soulseek_auto_tool.state import Session

def _match(user, name, **extra):
    return {"username": user, "filename": rf"music\{name}", "size": 1000, "extension": "mp3",
            "bitrate": 320, "free_slot": True, "queue_length": 0, **extra}


def _session(tmp_path, tracks):
    return Session(path=tmp_path / "s.json", playlist_url="u", playlist_name="Acid/Hard Tech", tracks=tracks)


def _track(id, query, matches):
    return Track(id=id, raw_title=query, uploader="u", query=query, searched=True, matches=matches)


def test_playlist_folder_name_matches_finder_style_and_is_safe():
    assert playlist_folder_name("Acid/Hard Tech") == "Acid:Hard Tech"
    assert playlist_folder_name("../escape") == ":escape"  # cannot climb out of the library
    assert "/" not in playlist_folder_name("a/b/c")
    assert not playlist_folder_name(".secret").startswith(".")
    assert playlist_folder_name("   ") == "playlist"


def _transfer_client(state_by_file, posted):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posted.append(request.url.path)
            return httpx.Response(201)
        files = [{"filename": f, "state": s} for f, s in state_by_file.items()]
        return httpx.Response(200, json={"directories": [{"directory": "music", "files": files}]})

    return SlskdClient("http://slskd", "k", transport=httpx.MockTransport(handler), sleep=lambda s: None)


def test_finished_download_is_filed_into_playlist_folder(tmp_path):
    downloads, library = tmp_path / "dl", tmp_path / "lib"
    (downloads / "music").mkdir(parents=True)
    (downloads / "music" / "[Phase] Song.mp3").write_bytes(b"audio")

    track = _track("1", "one", [])
    track.chosen, track.download_status = _match("peer", "[Phase] Song.mp3"), "chosen"
    session = _session(tmp_path, [track])
    posted = []
    client = _transfer_client({r"music\[Phase] Song.mp3": "Completed, Succeeded"}, posted)

    run_downloads(session, client, downloads, library, wait=0, sleep=lambda s: None)

    saved = library / "Acid:Hard Tech" / "[Phase] Song.mp3"
    assert saved.read_bytes() == b"audio"
    assert track.download_status == "done" and track.saved_path == str(saved)
    assert posted == ["/api/v0/transfers/downloads/peer"]
    assert not (downloads / "music" / "[Phase] Song.mp3").exists()


def test_existing_files_are_never_overwritten(tmp_path):
    downloads, library = tmp_path / "dl", tmp_path / "lib"
    (downloads).mkdir()
    (downloads / "Song.mp3").write_bytes(b"new")
    (library / "Acid:Hard Tech").mkdir(parents=True)
    (library / "Acid:Hard Tech" / "Song.mp3").write_bytes(b"old")

    track = _track("1", "one", [])
    track.chosen, track.download_status = _match("peer", "Song.mp3"), "chosen"
    session = _session(tmp_path, [track])
    client = _transfer_client({r"music\Song.mp3": "Completed, Succeeded"}, [])

    run_downloads(session, client, downloads, library, wait=0, sleep=lambda s: None)

    assert (library / "Acid:Hard Tech" / "Song.mp3").read_bytes() == b"old"
    assert (library / "Acid:Hard Tech" / "Song (1).mp3").read_bytes() == b"new"


def test_unfinished_download_stays_queued_for_next_run(tmp_path):
    track = _track("1", "one", [])
    track.chosen, track.download_status = _match("peer", "Song.mp3"), "chosen"
    session = _session(tmp_path, [track])
    client = _transfer_client({r"music\Song.mp3": "Queued, Remotely"}, [])

    run_downloads(session, client, tmp_path / "dl", tmp_path / "lib", wait=0, sleep=lambda s: None)

    assert track.download_status == "queued"
    assert Session.load(session.path).tracks[0].download_status == "queued"
