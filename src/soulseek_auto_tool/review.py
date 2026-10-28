from __future__ import annotations

from typing import Callable

from rich.console import Console

from .parser import build_query
from .state import Session

HELP = (
    "[dim]Enter[/dim]=accept  [dim]type text[/dim]=replace search  "
    "[dim]s[/dim]=skip  [dim]a[/dim]=accept all remaining  [dim]q[/dim]=save & quit"
)


def review_tracks(
    session: Session,
    console: Console,
    input_fn: Callable[[str], str] = input,
) -> bool:
    """Walk through pending tracks. Returns True when every track has been decided."""
    pending = [t for t in session.tracks if t.status == "pending"]
    if not pending:
        return True
    console.print(HELP)

    total = len(session.tracks)
    for track in pending:
        position = session.tracks.index(track) + 1
        console.print(f"\n[bold]{position}/{total}[/bold]  {track.raw_title}  [dim]by {track.uploader}[/dim]")
        flag = "" if track.confidence >= 0.7 else "  [yellow](low confidence, check this one)[/yellow]"
        console.print(f"   search: [cyan]{track.query}[/cyan]{flag}")

        answer = input_fn("   > ").strip()
        lowered = answer.lower()

        if lowered == "q":
            session.save()
            return False
        if lowered == "s":
            track.status = "skipped"
        elif lowered == "a":
            for rest in pending:
                if rest.status == "pending":
                    rest.status = "accepted"
            session.save()
            return True
        elif answer:
            track.query = build_query(answer, "")
            track.status = "accepted"
        else:
            track.status = "accepted"
        session.save()
    return True
