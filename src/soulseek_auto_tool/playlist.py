from __future__ import annotations

import re
import time
from html import unescape
from urllib.parse import urlsplit, urlunsplit

import httpx

from .models import Track

SHORT_HOST = "on.soundcloud.com"
LOOKUP_DELAY = 0.3  # seconds between per-track lookups


def resolve_url(url: str) -> str:
    """Expand SoundCloud share links (on.soundcloud.com/...) to the full playlist URL.

    yt-dlp doesn't follow these redirects. The tracking query string is dropped;
    the private-playlist secret lives in the path (".../s-XXXX"), so it is kept.
    """
    parts = urlsplit(url)
    if parts.netloc.lower() == SHORT_HOST:
        response = httpx.get(url, follow_redirects=False, timeout=15)
        location = response.headers.get("location")
        if not location:
            raise RuntimeError("That SoundCloud share link didn't redirect anywhere. Is it still valid?")
        parts = urlsplit(location)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def fetch_playlist(url: str) -> tuple[str, list[Track]]:
    """Fetch playlist metadata (no audio is downloaded) using yt-dlp."""
    import yt_dlp

    url = resolve_url(url)

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
    with yt_dlp.YoutubeDL(opts) as ydl:
        for entry in entries:
            if not entry:
                continue
            if not entry.get("title") and entry.get("url"):
                # Private/secret-link sets list only track URLs; look each one up.
                entry = _lookup_track(ydl, entry) or entry
                time.sleep(LOOKUP_DELAY)
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


def _lookup_track(ydl, entry: dict) -> dict | None:
    try:
        info = ydl.extract_info(entry["url"], download=False, process=False)
    except Exception:
        info = None
    # With ignoreerrors yt-dlp returns None on failure, e.g. "DRM protected" (SoundCloud
    # Go+) tracks. Their public page still shows a title, so read that instead.
    return info or scrape_track_page(entry["url"], entry.get("id"))


_TITLE_TAG = re.compile(r"<title>\s*Stream (.+?) by (.+?) \|", re.DOTALL)
_OG_TITLE = re.compile(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"')


def parse_track_page(html: str) -> tuple[str, str] | None:
    """Pull (title, uploader) out of a track page's <title>/og:title tags."""
    match = _TITLE_TAG.search(html)
    if not match:
        return None
    title, uploader = unescape(match.group(1)).strip(), unescape(match.group(2)).strip()
    og = _OG_TITLE.search(html)
    if og:  # og:title is the exact title; the <title> tag is just a fallback
        title = unescape(og.group(1)).strip() or title
    return title, uploader


def scrape_track_page(url: str, track_id: str | None = None) -> dict | None:
    try:
        response = httpx.get(
            url, follow_redirects=True, timeout=15, headers={"User-Agent": "Mozilla/5.0"}
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return None
    parsed = parse_track_page(response.text)
    if not parsed:
        return None
    title, uploader = parsed
    return {"id": track_id, "title": title, "uploader": uploader, "webpage_url": url}
