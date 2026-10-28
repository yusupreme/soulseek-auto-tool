from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    slskd_url: str
    slskd_api_key: str
    library_dir: Path  # where finished playlists are filed, one folder per playlist
    slskd_downloads_dir: Path  # slskd's own download folder (files are moved out of it)


def load_settings() -> Settings:
    """Read settings from the environment (and a local .env file if present)."""
    load_dotenv()
    return Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        slskd_url=os.getenv("SLSKD_URL", "http://localhost:5030").rstrip("/"),
        slskd_api_key=os.getenv("SLSKD_API_KEY", "").strip(),
        library_dir=Path(os.getenv("LIBRARY_DIR", "~/soundcloud downloads")).expanduser(),
        slskd_downloads_dir=Path(os.getenv("SLSKD_DOWNLOADS_DIR", "~/slskd/downloads")).expanduser(),
    )
