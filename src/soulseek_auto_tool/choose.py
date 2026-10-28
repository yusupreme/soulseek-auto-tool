from __future__ import annotations

import re
from typing import Callable

from rich.console import Console
from rich.markup import escape

from .models import Track
from .parser import build_query
from .state import Session

PAGE_SIZE = 5
CLOSE_SECONDS = 3  # lengths this close count as the same track
FAR_SECONDS = 10  # lengths this far apart are very likely a different version

_SNIPPET = re.compile(r"snippet|preview|teaser", re.IGNORECASE)

HELP = (
    "[dim]Enter[/dim]=take #1  [dim]number[/dim]=pick that file  [dim]m[/dim]=more results  "
    "[dim]e[/dim]=edit search & retry  [dim]s[/dim]=skip track  [dim]q[/dim]=save & quit"
)


def fmt_time(seconds: float | None) -> str:
    if seconds is None:
        return "?:??"
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def length_difference(soundcloud: float | None, soulseek: float | None) -> tuple[str, str]:
    """Return (text like "+0:12", rich style) comparing the two track lengths."""
    if soundcloud is None or soulseek is None:
        return "", "dim"
    diff = soulseek - soundcloud
    text = f"{'+' if diff >= 0 else '-'}{fmt_time(abs(diff))}"
    gap = abs(diff)
    style = "green" if gap <= CLOSE_SECONDS else "yellow" if gap <= FAR_SECONDS else "red"
    return text, style


def is_snippet(track: Track) -> bool:
    return bool(_SNIPPET.search(track.raw_title))


def _filename(path: str) -> str:
    return re.split(r"[\\/]", path)[-1]


def render_card(track: Track, position: int, total: int, page: int, console: Console) -> None:
    """Print the SoundCloud track and one page of Soulseek matches side by side."""
    console.print(
        f"\n[bold]{position}/{total}[/bold]  SoundCloud: [bold]{escape(track.raw_title)}[/bold]"
        f"  [dim]by {escape(track.uploader)}[/dim]  [bold]{fmt_time(track.duration)}[/bold]"
    )
    if track.url:
        console.print(f"   [dim]{escape(track.url)}[/dim]")
    console.print(f"   searched: [cyan]{escape(track.query)}[/cyan]")

    if not track.matches:
        console.print("   [yellow]No 320 kbps MP3 matches.[/yellow] Try [dim]e[/dim] to edit the search, or [dim]s[/dim] to skip.")
        return
    if is_snippet(track):
        console.print("   [dim]SoundCloud marks this as a snippet/preview, so a longer file is expected.[/dim]")

    start = page * PAGE_SIZE
    for index in range(start, min(start + PAGE_SIZE, len(track.matches))):
        m = track.matches[index]
        diff_text, style = length_difference(track.duration, m.get("length"))
        if is_snippet(track):
            style = "dim"
        slot = "free slot" if m["free_slot"] else f"queue {m['queue_length']}"
        console.print(
            f"  {index + 1:>2}. {escape(_filename(m['filename']))}\n"
            f"      {fmt_time(m.get('length'))} [{style}]{diff_text:>7}[/{style}]   "
            f"{(m.get('size') or 0) / 1_048_576:.1f} MB   {slot}   [dim]{escape(m['username'])}[/dim]"
        )
    shown_to = min(start + PAGE_SIZE, len(track.matches))
    if shown_to < len(track.matches):
        console.print(f"  [dim]({len(track.matches) - shown_to} more, press m)[/dim]")


def choose_matches(
    session: Session,
    console: Console,
    input_fn: Callable[[str], str] = input,
    retry: Callable[[Track], None] | None = None,
) -> bool:
    """Go through every searched track and let the user decide what, if anything, to download.

    Returns True when every track has been decided, False if the user quit.
    """
    for track in session.tracks:  # failed downloads get another chance
        if track.download_status == "failed":
            track.download_status, track.chosen = "", None
    todo = [t for t in session.tracks if t.searched and not t.download_status]
    if not todo:
        return True
    console.print(HELP)

    for track in todo:
        position = session.tracks.index(track) + 1
        page = 0
        while True:
            render_card(track, position, len(session.tracks), page, console)
            answer = input_fn("   > ").strip().lower()

            if answer == "q":
                session.save()
                return False
            if answer == "s":
                track.download_status = "skipped"
                break
            if answer == "m":
                if (page + 1) * PAGE_SIZE < len(track.matches):
                    page += 1
                else:
                    console.print("   [dim]No more results.[/dim]")
                continue
            if answer == "e":
                if retry is None:
                    console.print("   [dim]Retrying is not available here.[/dim]")
                    continue
                text = input_fn("   new search > ").strip()
                if text:
                    track.query = build_query(text, "")
                    track.matches = []
                    console.print("   searching...")
                    retry(track)
                    page = 0
                continue

            if answer == "":
                index = 0
            elif answer.isdigit():
                index = int(answer) - 1
            else:
                console.print("   [dim]Not sure what that means. See the options above.[/dim]")
                continue
            if not 0 <= index < len(track.matches):
                console.print("   [dim]Pick one of the numbers shown.[/dim]")
                continue

            track.chosen, track.download_status, track.picked_by = track.matches[index], "chosen", "user"
            break
        session.save()
    return True
