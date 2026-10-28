from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from typing import Callable

from rich.console import Console

from .slskd import SlskdClient
from .state import Session

MAX_CHOICES = 5


def playlist_folder_name(name: str) -> str:
    """Folder name for a playlist. "/" becomes ":" which Finder displays as "/"."""
    cleaned = name.replace("/", ":").replace("\x00", "").strip().lstrip(".")
    return cleaned or "playlist"


def _basename(path: str) -> str:
    return re.split(r"[\\/]", path)[-1]


def choose_matches(
    session: Session, console: Console, input_fn: Callable[[str], str] = input
) -> bool:
    """Let the user pick which match to download for each searched track.

    Returns True when every track has been decided, False if the user quit.
    """
    todo = [t for t in session.tracks if t.searched and t.matches and not t.download_status]
    if not todo:
        return True
    console.print(
        "\n[dim]Enter[/dim]=best match  [dim]1-5[/dim]=pick that one  [dim]s[/dim]=skip  "
        "[dim]a[/dim]=best match for all remaining  [dim]q[/dim]=save & quit"
    )
    for track in todo:
        console.print(f"\n[bold]{track.query}[/bold]")
        for i, m in enumerate(track.matches[:MAX_CHOICES], start=1):
            fmt = m["extension"] + (f" {m['bitrate']}k" if m.get("bitrate") else "")
            slot = "free slot" if m["free_slot"] else f"queue {m['queue_length']}"
            console.print(f"  {i}. {_basename(m['filename'])}  [dim]{fmt}, {m['username']}, {slot}[/dim]")
        answer = input_fn("   > ").strip().lower()

        if answer == "q":
            session.save()
            return False
        if answer == "a":
            for rest in todo:
                if not rest.download_status:
                    rest.chosen, rest.download_status = rest.matches[0], "chosen"
            session.save()
            return True
        if answer == "s":
            track.download_status = "skipped"
        else:
            index = int(answer) - 1 if answer.isdigit() else 0
            if not 0 <= index < min(len(track.matches), MAX_CHOICES):
                index = 0
            track.chosen, track.download_status = track.matches[index], "chosen"
        session.save()
    return True


def _find_download(downloads_dir: Path, remote_filename: str) -> Path | None:
    """Find a finished download in slskd's folder (newest file with that name)."""
    wanted = _basename(remote_filename)
    found = []
    for root, _, files in os.walk(downloads_dir):
        if wanted in files:
            found.append(Path(root) / wanted)
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def _move_into(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / src.name
    counter = 1
    while target.exists():  # never overwrite a file you already have
        target = dest_dir / f"{src.stem} ({counter}){src.suffix}"
        counter += 1
    shutil.move(str(src), str(target))
    return target


def run_downloads(
    session: Session,
    client: SlskdClient,
    downloads_dir: Path,
    library_dir: Path,
    *,
    wait: float = 600,
    poll: float = 5,
    sleep: Callable[[float], None] = time.sleep,
    on_event: Callable[[str], None] = lambda message: None,
) -> None:
    """Queue chosen downloads in slskd and file finished ones under <library>/<playlist>/.

    Waits up to `wait` seconds. Anything still queued stays queued in slskd and is
    filed the next time the tool is run for this playlist.
    """
    dest = library_dir / playlist_folder_name(session.playlist_name)

    by_user: dict[str, list] = {}
    for track in session.tracks:
        if track.download_status == "chosen" and track.chosen:
            by_user.setdefault(track.chosen["username"], []).append(track)
    for username, tracks in by_user.items():
        client.queue_download(
            username,
            [{"filename": t.chosen["filename"], "size": t.chosen.get("size") or 0} for t in tracks],
        )
        for t in tracks:
            t.download_status = "queued"
        on_event(f"Queued {len(tracks)} file(s) from {username}")
    session.save()

    waited = 0.0
    while True:
        pending = [t for t in session.tracks if t.download_status == "queued" and t.chosen]
        if not pending:
            return
        for username in {t.chosen["username"] for t in pending}:
            states = {f["filename"]: f.get("state", "") for f in client.list_downloads(username)}
            for track in (t for t in pending if t.chosen["username"] == username):
                if "Succeeded" not in states.get(track.chosen["filename"], ""):
                    continue
                source = _find_download(downloads_dir, track.chosen["filename"])
                if source:
                    track.saved_path = str(_move_into(source, dest))
                    track.download_status = "done"
                    on_event(f"Saved {Path(track.saved_path).name}")
        session.save()
        if waited >= wait or not any(t.download_status == "queued" for t in session.tracks):
            return
        sleep(poll)
        waited += poll
