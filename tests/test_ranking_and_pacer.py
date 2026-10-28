import pytest

from soulseek_auto_tool.pacer import Pacer
from soulseek_auto_tool.ranking import rank_responses


def _response(username, files, free=True, queue=0, speed=1_000_000):
    return {
        "username": username,
        "hasFreeUploadSlot": free,
        "queueLength": queue,
        "uploadSpeed": speed,
        "files": files,
    }


def test_flac_with_free_slot_beats_low_bitrate_mp3():
    responses = [
        _response("mp3guy", [{"filename": r"m\Daft Punk - One More Time.mp3", "bitRate": 128}], free=False, queue=20),
        _response("flacguy", [{"filename": r"m\Daft Punk - One More Time.flac", "size": 30_000_000}]),
    ]
    ranked = rank_responses(responses, "Daft Punk One More Time")
    assert ranked[0]["username"] == "flacguy"


def test_non_audio_and_unrelated_files_are_dropped():
    responses = [
        _response("a", [{"filename": r"x\One More Time.jpg"}]),
        _response("b", [{"filename": r"x\Completely Different Song.mp3", "bitRate": 320}]),
    ]
    assert rank_responses(responses, "Daft Punk One More Time") == []


def test_duration_match_boosts_score():
    files = lambda length: [{"filename": "Daft Punk - One More Time.mp3", "bitRate": 320, "length": length}]
    close = rank_responses([_response("a", files(320))], "Daft Punk One More Time", duration=321)
    far = rank_responses([_response("a", files(120))], "Daft Punk One More Time", duration=321)
    assert close[0]["score"] > far[0]["score"]


def test_limit_is_respected():
    responses = [
        _response(f"u{i}", [{"filename": "A - B.mp3", "bitRate": 320}]) for i in range(10)
    ]
    assert len(rank_responses(responses, "A B", limit=3)) == 3


def test_pacer_waits_between_calls_but_not_before_the_first():
    now = [0.0]
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    pacer = Pacer(3, 4, sleep=sleep, clock=lambda: now[0], uniform=lambda a, b: 3.5)
    pacer.wait()
    assert slept == []
    pacer.wait()
    assert slept == [3.5]
    now[0] += 10  # plenty of time passed on its own
    pacer.wait()
    assert slept == [3.5]


def test_pacer_rejects_bad_range():
    with pytest.raises(ValueError):
        Pacer(5, 2)
