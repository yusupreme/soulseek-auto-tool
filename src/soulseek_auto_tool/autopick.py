from __future__ import annotations

import re

from rich.console import Console
from rich.markup import escape

from .choose import fmt_time, is_snippet, length_difference
from .ranking import _tokens, name_overlap
from .state import Session

AUTO_TOLERANCE = 3  # seconds; the same "close" limit the review cards color green

# Words that mark a different version of a song. A file that has one the SoundCloud title doesn't is not auto-picked.
VERSION_WORDS = {
    "remix", "edit", "dub", "vip", "bootleg", "mashup", "live", "instrumental", "acapella", "acappella",
    "rework", "refix", "flip", "cover", "reprise", "version", "radio", "extended", "club", "demo",
}


def _basename(path: str) -> str:
    return re.split(r"[\\/]", path)[-1]


def auto_pick(track, tolerance: float = AUTO_TOLERANCE) -> dict | None:
    """The match to take without asking, or None when a person should decide.

    A match is a high-probability one when every word of the search is in its file name, it has no version word
    (remix, edit, live...) that the SoundCloud title lacks, and its length is within `tolerance` seconds of the
    SoundCloud track. Of those, the largest file wins (matches are already sorted that way).
    Snippets and tracks with an unknown length are never auto-picked.
    """
    if not track.matches or not track.duration or is_snippet(track):
        return None
    allowed = _tokens(track.raw_title) | _tokens(track.title) | _tokens(track.query)
    for match in track.matches:
        length = match.get("length")
        if length is None or abs(length - track.duration) > tolerance:
            continue
        name = _basename(match["filename"])
        if name_overlap(name, track.query) < 1.0:
            continue
        if (_tokens(name) & VERSION_WORDS) - allowed:
            continue
        return match
    return None


def auto_select(session: Session, console: Console, tolerance: float = AUTO_TOLERANCE) -> int:
    """Choose the high-probability matches automatically. Returns how many were picked."""
    todo = [t for t in session.tracks if t.searched and not t.download_status and t.matches]
    picked = 0
    for track in todo:
        match = auto_pick(track, tolerance)
        if match is None:
            continue
        track.chosen, track.download_status, track.picked_by = match, "chosen", "auto"
        picked += 1
        diff, style = length_difference(track.duration, match.get("length"))
        console.print(
            f"[green]auto[/green] {session.tracks.index(track) + 1}. {escape(track.raw_title)} "
            f"[dim]->[/dim] {escape(_basename(match['filename']))} "
            f"[dim]{fmt_time(match.get('length'))} [{style}]{diff}[/{style}], "
            f"{(match.get('size') or 0) / 1_048_576:.1f} MB, {escape(match['username'])}[/dim]"
        )
    if picked:
        session.save()
    left = sum(1 for t in todo if not t.download_status)
    console.print(f"\nAuto-selected {picked} high-probability track(s). {left} with matches need your decision.")
    return picked
