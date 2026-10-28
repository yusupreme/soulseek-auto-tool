from __future__ import annotations

from .models import Track


def fetch_playlist(url: str) -> tuple[str, list[Track]]:
    """Fetch playlist metadata (no audio is downloaded) using yt-dlp."""
    import yt_dlp

    opts = {
        "extract_flat": True,
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise RuntimeError("Could not read that playlist. Is the URL correct and public?")

    entries = info.get("entries") or [info]
    tracks: list[Track] = []
    for entry in entries:
        if not entry:
            continue
        tracks.append(
            Track(
                id=str(entry.get("id") or entry.get("url")),
                raw_title=(entry.get("title") or "").strip(),
                uploader=(entry.get("uploader") or entry.get("channel") or "").strip(),
                url=entry.get("webpage_url") or entry.get("url") or "",
                duration=entry.get("duration"),
            )
        )
    return info.get("title") or "playlist", tracks
