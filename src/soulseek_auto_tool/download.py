from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from typing import Callable

from .autopick import auto_pick
from .fileinfo import quality_problem, read_audio_info
from .slskd import SlskdClient
from .state import Session


def playlist_folder_name(name: str) -> str:
    """Folder name for a playlist. "/" becomes ":" which Finder displays as "/"."""
    cleaned = name.replace("/", ":").replace("\x00", "").strip().lstrip(".")
    return cleaned or "playlist"


def _basename(path: str) -> str:
    return re.split(r"[\\/]", path)[-1]


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


def _prune_empty_dirs(directory: Path, stop: Path) -> None:
    """Remove folders slskd left behind once their file has been moved out."""
    while directory != stop and stop in directory.parents:
        try:
            directory.rmdir()  # only succeeds when the folder is empty
        except OSError:
            return
        directory = directory.parent


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

    def queue_chosen() -> None:
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

    def reject(track, source: Path, reason: str) -> None:
        """Delete a download that is not a real 320 kbps CBR MP3 and move on to the next safe match."""
        bad = track.chosen
        name = _basename(bad["filename"])
        source.unlink(missing_ok=True)
        _prune_empty_dirs(source.parent, downloads_dir)
        track.rejected.append({"username": bad["username"], "filename": bad["filename"], "reason": reason})
        track.matches = [m for m in track.matches if (m["username"], m["filename"]) != (bad["username"], bad["filename"])]
        nxt = auto_pick(track)
        if nxt:
            track.chosen, track.download_status = nxt, "chosen"
            on_event(f"Rejected {name} ({reason}); trying {_basename(nxt['filename'])} from {nxt['username']}")
        else:
            track.download_status, track.download_note = "failed", f"rejected: {reason}"
            on_event(f"Rejected {name} ({reason}); no other safe match, left for you")

    queue_chosen()

    waited = 0.0
    while True:
        pending = [t for t in session.tracks if t.download_status == "queued" and t.chosen]
        if not pending:
            return
        for username in {t.chosen["username"] for t in pending}:
            states = {f["filename"]: f.get("state", "") for f in client.list_downloads(username)}
            for track in (t for t in pending if t.chosen["username"] == username):
                state = states.get(track.chosen["filename"], "")
                if "Succeeded" in state:
                    source = _find_download(downloads_dir, track.chosen["filename"])
                    if source:
                        info = read_audio_info(source)
                        problem = quality_problem(info)
                        if problem:
                            reject(track, source, problem)
                            continue
                        track.saved_path = str(_move_into(source, dest))
                        track.file_info = info
                        track.download_status = "done"
                        _prune_empty_dirs(source.parent, downloads_dir)
                        on_event(f"Saved {Path(track.saved_path).name}")
                elif "Completed" in state:  # cancelled, rejected, timed out, errored...
                    track.download_status, track.download_note = "failed", state
                    on_event(f"Failed ({state}): {_basename(track.chosen['filename'])}")
        queue_chosen()  # files that replaced a rejected one
        if waited >= wait or not any(t.download_status == "queued" for t in session.tracks):
            return
        sleep(poll)
        waited += poll
