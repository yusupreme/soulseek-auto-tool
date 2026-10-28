from pathlib import Path

from soulseek_auto_tool.download import run_downloads
from soulseek_auto_tool.fileinfo import read_audio_info
from soulseek_auto_tool.models import Track
from soulseek_auto_tool.ranking import summarize_responses
from soulseek_auto_tool.report import categorize, file_flags, write_log
from soulseek_auto_tool.state import Session
from test_download import _match, _transfer_client


def _mp3_bytes(frames=60, kbps=128):
    """A tiny but valid CBR / 44.1 kHz / stereo MP3 (silent frames)."""
    index, size = {128: (0x90, 417), 320: (0xE0, 1044)}[kbps]
    return (bytes([0xFF, 0xFB, index, 0x00]) + bytes(size - 4)) * frames


def test_read_audio_info_reads_real_properties(tmp_path):
    path = tmp_path / "a.mp3"
    path.write_bytes(_mp3_bytes())
    info = read_audio_info(path)
    assert info["bitrate_mode"] in ("CBR", None)  # silent test frames; never a crash
    assert info["bitrate_kbps"] == 128 and info["sample_rate"] == 44100 and info["channels"] == 2
    assert info["size_bytes"] == path.stat().st_size and info["length"] > 0


def test_read_audio_info_survives_garbage(tmp_path):
    path = tmp_path / "bad.mp3"
    path.write_bytes(b"not audio at all")
    assert read_audio_info(path)["error"]


def _track(**kw):
    base = dict(id="1", raw_title="Artist - Song", uploader="up", query="Artist Song", searched=True, status="accepted")
    return Track(**{**base, **kw})


def test_categorize_covers_every_outcome():
    assert categorize(_track(download_status="done")) == "downloaded"
    assert categorize(_track(download_status="queued")) == "queued"
    assert categorize(_track(download_status="failed")) == "failed"
    assert categorize(_track(searched=False, status="skipped")) == "skipped_terms"
    assert categorize(_track(searched=False)) == "not_searched"
    assert categorize(_track(matches=[])) == "not_found"
    assert categorize(_track(matches=[{}], download_status="skipped")) == "skipped"
    assert categorize(_track(matches=[{}])) == "undecided"


def test_file_flags_point_out_the_suspicious_things():
    ok = _track(duration=300, file_info={"bitrate_kbps": 320, "bitrate_mode": "CBR", "sample_rate": 44100, "length": 301})
    assert file_flags(ok) == []
    bad = _track(
        duration=300, chosen={"length": 500},
        file_info={"bitrate_kbps": 245, "bitrate_mode": "VBR", "sample_rate": 48000, "length": 420},
    )
    text = " | ".join(file_flags(bad))
    assert "245 kbps" in text and "VBR" in text and "48000" in text
    assert "differs from SoundCloud by 2:00" in text and "sender reported a different length" in text


def test_snippet_length_difference_is_not_flagged():
    snippet = _track(raw_title="Song SNIPPET", duration=60, file_info={"bitrate_kbps": 320, "length": 400})
    assert file_flags(snippet) == []


def test_summarize_explains_why_nothing_matched():
    responses = [{"files": [
        {"filename": r"x\tribe_vibes.mp3", "bitRate": 320},
        {"filename": r"x\other.flac"}, {"filename": r"x\cover.jpg"}, {"filename": r"x\low.mp3", "bitRate": 128},
    ]}]
    stats = summarize_responses(responses, "Completely Different Words")
    assert stats["peers"] == 1 and stats["files"] == 4
    assert stats["formats"] == {"mp3 320": 1, "flac": 1, "mp3 other": 1}
    assert stats["mp3_320_name_mismatch"] == 1


def test_full_log_lists_downloaded_details_and_every_other_outcome(tmp_path):
    downloads, library = tmp_path / "dl", tmp_path / "lib"
    (downloads / "music").mkdir(parents=True)
    (downloads / "music" / "Song.mp3").write_bytes(_mp3_bytes(kbps=320))

    done = _track(id="1", raw_title="Artist - Song", duration=300)
    done.chosen, done.download_status = _match("peer", "Song.mp3"), "chosen"
    nothing = _track(id="2", raw_title="Rare - Track", query="Rare Track", matches=[],
                     search_stats={"peers": 0, "files": 0, "formats": {}, "mp3_320_name_mismatch": 0})
    passed = _track(id="3", raw_title="Meh - Song", matches=[{}], download_status="skipped")
    session = Session(path=tmp_path / "s.json", playlist_url="u", playlist_name="Acid/Hard Tech",
                      tracks=[done, nothing, passed])

    client = _transfer_client({r"music\Song.mp3": "Completed, Succeeded"}, [])
    run_downloads(session, client, downloads, library, wait=0, sleep=lambda s: None)
    assert not (downloads / "music").exists()  # empty folder cleaned up

    md = write_log(session, tmp_path / "out")
    text = md.read_text()
    assert md.parent.name == "Acid-Hard Tech"
    assert "| Downloaded | 1 |" in text and "| Not found (no 320 kbps MP3 match) | 1 |" in text
    assert "320 kbps" in text and "44100 Hz" in text and "| auto |" not in text
    assert "no one answered the search" in text and "Rare - Track" in text
    assert "Skipped by you" in text and "Meh - Song" in text
    csv_text = (md.parent / "downloaded.csv").read_text()
    assert "actual_bitrate_kbps" in csv_text and "peer" in csv_text and "320" in csv_text
    assert (md.parent / "tracks.json").exists()


def test_failed_transfer_is_logged_with_the_reason(tmp_path):
    track = _track(id="1")
    track.chosen, track.download_status = _match("peer", "Song.mp3"), "chosen"
    session = Session(path=tmp_path / "s.json", playlist_url="u", playlist_name="Mix", tracks=[track])
    client = _transfer_client({r"music\Song.mp3": "Completed, TimedOut"}, [])

    run_downloads(session, client, tmp_path / "dl", tmp_path / "lib", wait=0, sleep=lambda s: None)

    assert track.download_status == "failed" and track.download_note == "Completed, TimedOut"
    assert "reason: Completed, TimedOut" in write_log(session, tmp_path / "out").read_text()


def _two_file_session(tmp_path, first_kbps, second_kbps=320):
    downloads, library = tmp_path / "dl", tmp_path / "lib"
    (downloads / "music").mkdir(parents=True)
    (downloads / "music" / "Artist - Song.mp3").write_bytes(_mp3_bytes(kbps=first_kbps))
    (downloads / "music" / "Artist - Song 2.mp3").write_bytes(_mp3_bytes(kbps=second_kbps))
    track = _track(id="1", raw_title="Artist - Song", duration=1.5,
                   matches=[_match("u1", "Artist - Song.mp3", length=1.5, size=2000),
                            _match("u2", "Artist - Song 2.mp3", length=1.5, size=1000)])
    track.chosen, track.download_status = track.matches[0], "chosen"
    session = Session(path=tmp_path / "s.json", playlist_url="u", playlist_name="Mix", tracks=[track])
    states = {r"music\Artist - Song.mp3": "Completed, Succeeded", r"music\Artist - Song 2.mp3": "Completed, Succeeded"}
    return session, track, downloads, library, states


def test_fake_320_is_deleted_and_the_next_safe_match_is_downloaded(tmp_path):
    session, track, downloads, library, states = _two_file_session(tmp_path, first_kbps=128)
    posted, events = [], []
    client = _transfer_client(states, posted)

    run_downloads(session, client, downloads, library, wait=10, sleep=lambda s: None, on_event=events.append)

    assert posted == ["/api/v0/transfers/downloads/u1", "/api/v0/transfers/downloads/u2"]
    assert [f.name for f in (library / "Mix").iterdir()] == ["Artist - Song 2.mp3"]
    assert not (downloads / "music" / "Artist - Song.mp3").exists()  # the 128 kbps file is gone
    assert track.download_status == "done" and track.chosen["username"] == "u2"
    assert track.rejected[0]["username"] == "u1" and "128 kbps" in track.rejected[0]["reason"]
    assert [m["username"] for m in track.matches] == ["u2"]
    assert any("Rejected Artist - Song.mp3" in e and "trying Artist - Song 2.mp3" in e for e in events)

    text = write_log(session, tmp_path / "out").read_text()
    assert "Rejected after download" in text and "real bitrate is 128 kbps (file deleted)" in text


def test_rejected_file_with_no_safe_replacement_is_left_for_the_user(tmp_path):
    session, track, downloads, library, states = _two_file_session(tmp_path, first_kbps=128)
    track.matches = track.matches[:1]  # nothing else to fall back to

    run_downloads(session, _transfer_client(states, []), downloads, library, wait=10, sleep=lambda s: None)

    assert track.download_status == "failed" and track.download_note.startswith("rejected: real bitrate is 128")
    assert track.matches == [] and not (library / "Mix").exists()
    assert "Rejected after download" in write_log(session, tmp_path / "out").read_text()


def test_genuine_320_is_kept_and_unreadable_files_are_not_judged(tmp_path):
    from soulseek_auto_tool.fileinfo import quality_problem

    session, track, downloads, library, states = _two_file_session(tmp_path, first_kbps=320)
    run_downloads(session, _transfer_client(states, []), downloads, library, wait=0, sleep=lambda s: None)
    assert track.download_status == "done" and track.rejected == []

    assert quality_problem({"error": "could not read audio properties"}) is None
    assert quality_problem({"bitrate_kbps": 320, "bitrate_mode": "CBR"}) is None
    assert quality_problem({"bitrate_kbps": 320, "bitrate_mode": None}) is None
    assert "VBR" in quality_problem({"bitrate_kbps": 320, "bitrate_mode": "VBR"})
    assert "256" in quality_problem({"bitrate_kbps": 256, "bitrate_mode": "CBR"})
