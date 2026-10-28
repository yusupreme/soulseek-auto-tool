import pytest

from soulseek_auto_tool.pacer import Pacer
from soulseek_auto_tool.ranking import rank_responses

QUERY = "Daft Punk One More Time"


def _response(username, files, free=True, queue=0, speed=1_000_000):
    return {
        "username": username,
        "hasFreeUploadSlot": free,
        "queueLength": queue,
        "uploadSpeed": speed,
        "files": files,
    }


def _file(name="Daft Punk - One More Time", ext="mp3", bitrate=320, size=10_000_000):
    return {"filename": rf"m\{name}.{ext}", "bitRate": bitrate, "size": size}


def _users(ranked):
    return [m["username"] for m in ranked]


def test_only_320_mp3s_are_returned_even_if_other_files_are_much_bigger():
    responses = [
        _response("flac", [_file(ext="flac", bitrate=None, size=40_000_000)]),
        _response("mp3_256", [_file(bitrate=256, size=50_000_000)]),
        _response("vbr_v0", [_file(bitrate=245, size=60_000_000)]),
        _response("unknown_rate", [_file(bitrate=None, size=70_000_000)]),
        _response("wav", [_file(ext="wav", bitrate=None, size=90_000_000)]),
        _response("mp3_320", [_file(bitrate=320, size=9_000_000)]),
    ]
    assert _users(rank_responses(responses, QUERY)) == ["mp3_320"]


def test_no_320_mp3_means_no_matches():
    responses = [_response("a", [_file(bitrate=256), _file(ext="flac", bitrate=None)])]
    assert rank_responses(responses, QUERY) == []


def test_among_320_mp3s_the_largest_file_wins():
    responses = [
        _response("small", [_file(size=8_000_000)]),
        _response("large", [_file(size=14_000_000)]),
        _response("medium", [_file(size=11_000_000)]),
    ]
    assert _users(rank_responses(responses, QUERY)) == ["large", "medium", "small"]


def test_free_slot_and_queue_only_break_size_ties():
    responses = [
        _response("busy", [_file(size=10)], free=False, queue=30),
        _response("free", [_file(size=10)], free=True, queue=0),
        _response("bigger_but_busy", [_file(size=11)], free=False, queue=30),
    ]
    assert _users(rank_responses(responses, QUERY)) == ["bigger_but_busy", "free", "busy"]


def test_a_huge_file_that_does_not_match_the_search_is_ignored():
    responses = [
        _response("wrong", [_file(name="Daft Punk - Harder Better Faster", size=90_000_000)]),
        _response("right", [_file(size=10_000_000)]),
    ]
    assert _users(rank_responses(responses, QUERY)) == ["right"]


def test_non_audio_and_unrelated_files_are_dropped():
    responses = [
        _response("a", [{"filename": r"x\One More Time.jpg", "size": 5}]),
        _response("b", [_file(name="Completely Different Song")]),
    ]
    assert rank_responses(responses, QUERY) == []


def test_limit_is_respected():
    responses = [_response(f"u{i}", [_file(size=i)]) for i in range(10)]
    assert len(rank_responses(responses, QUERY, limit=3)) == 3


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
