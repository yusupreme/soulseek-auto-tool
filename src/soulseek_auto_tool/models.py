from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Track:
    id: str
    raw_title: str
    uploader: str
    url: str = ""
    duration: float | None = None
    artist: str = ""
    title: str = ""
    confidence: float = 0.0
    query: str = ""
    status: str = "pending"  # pending | accepted | skipped
    searched: bool = False
    matches: list[dict] = field(default_factory=list)
    chosen: dict | None = None
    picked_by: str = ""  # "auto" | "user"
    download_status: str = ""  # "" | skipped | chosen | queued | done | failed
    saved_path: str = ""
    download_note: str = ""  # why a download failed
    file_info: dict = field(default_factory=dict)  # real properties of the saved file
    rejected: list[dict] = field(default_factory=list)  # downloaded files deleted for not being 320 kbps CBR
    search_stats: dict = field(default_factory=dict)  # what the last search returned

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Track":
        return cls(**data)
