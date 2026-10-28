from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .models import Track


def session_path(state_dir: Path, playlist_url: str) -> Path:
    digest = hashlib.sha1(playlist_url.encode()).hexdigest()[:10]
    return state_dir / f"{digest}.json"


@dataclass
class Session:
    """A playlist run, saved to disk so it can be stopped and resumed."""

    path: Path
    playlist_url: str
    playlist_name: str = ""
    tracks: list[Track] = field(default_factory=list)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "playlist_url": self.playlist_url,
            "playlist_name": self.playlist_name,
            "tracks": [t.to_dict() for t in self.tracks],
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        os.replace(tmp, self.path)  # atomic: never leaves a half-written file

    @classmethod
    def load(cls, path: Path) -> "Session":
        data = json.loads(path.read_text())
        return cls(
            path=path,
            playlist_url=data["playlist_url"],
            playlist_name=data.get("playlist_name", ""),
            tracks=[Track.from_dict(t) for t in data["tracks"]],
        )
