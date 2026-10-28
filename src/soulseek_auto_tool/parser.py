from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .models import Track

AI_MODEL = "claude-haiku-5-5"
AI_BATCH_SIZE = 50

# Words that, when they make up a whole [bracket] or (paren) group, are promo noise.
_JUNK_WORDS = {
    "free", "dl", "download", "free dl", "free download", "premiere", "out now",
    "buy", "hq", "hd", "official", "official audio", "official video", "audio",
    "video", "lyrics", "lyric video", "exclusive", "preview", "snippet",
    "supported by", "click buy", "clip", "teaser", "new", "release", "out soon",
}
_GROUP = re.compile(r"[\[(]([^\[\]()]*)[\])]")
_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF️‍]+"
)
_SEPARATOR = re.compile(r"\s+[-–—]\s+")
_TRAILING_PROMO = re.compile(r"\b(free\s*(dl|download)|out now)\b.*$", re.IGNORECASE)


@dataclass
class Parsed:
    artist: str
    title: str
    confidence: float


def _is_junk(group_text: str) -> bool:
    text = re.sub(r"[^a-z ]", " ", group_text.lower())
    text = re.sub(r"\s+", " ", text).strip()
    return text in _JUNK_WORDS or text.startswith(("free", "out now", "buy"))


def clean_title(raw: str) -> str:
    """Strip emojis and promo tags like [FREE DL] while keeping (Remix) info."""
    text = _EMOJI.sub("", raw)
    text = _GROUP.sub(lambda m: "" if _is_junk(m.group(1)) else m.group(0), text)
    text = _TRAILING_PROMO.sub("", text)
    return re.sub(r"\s+", " ", text).strip(" -–—|•")


def parse_title(raw_title: str, uploader: str) -> Parsed:
    """Regex-based guess at (artist, title). Used by default without an API key."""
    cleaned = clean_title(raw_title)
    parts = _SEPARATOR.split(cleaned, maxsplit=1)
    if len(parts) == 2 and parts[0] and parts[1]:
        return Parsed(parts[0].strip(), parts[1].strip(), 0.8)
    # No "Artist - Title" pattern: assume the uploader is the artist.
    return Parsed(uploader.strip(), cleaned, 0.4)


def build_query(artist: str, title: str) -> str:
    """Turn artist + title into a Soulseek-friendly search string.

    Soulseek treats a leading "-" as "exclude this word", and punctuation hurts
    matching, so everything except letters, digits and apostrophes is removed.
    """
    text = f"{artist} {title}".replace("’", "'")
    text = re.sub(r"[^\w' ]", " ", text, flags=re.UNICODE).replace("_", " ")
    return re.sub(r"\s+", " ", text).strip()


def apply_regex_parse(tracks: list[Track]) -> None:
    for track in tracks:
        parsed = parse_title(track.raw_title, track.uploader)
        _apply(track, parsed.artist, parsed.title, parsed.confidence)


def _apply(track: Track, artist: str, title: str, confidence: float) -> None:
    track.artist, track.title, track.confidence = artist, title, confidence
    track.query = build_query(artist, title)


# ---------------------------------------------------------------- AI parsing

_TOOL = {
    "name": "report_tracks",
    "description": "Report the parsed artist and title for each SoundCloud track.",
    "input_schema": {
        "type": "object",
        "properties": {
            "tracks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "artist": {"type": "string"},
                        "title": {
                            "type": "string",
                            "description": "Track title, including remix/edit info if present.",
                        },
                        "confidence": {"type": "number", "description": "0.0 to 1.0"},
                    },
                    "required": ["id", "artist", "title", "confidence"],
                },
            }
        },
        "required": ["tracks"],
    },
}

_SYSTEM = (
    "You clean up SoundCloud track metadata so tracks can be searched on Soulseek. "
    "For each track, return the real artist and the track title. Remove promo noise "
    "(FREE DL, emojis, 'Premiere', etc.) but keep remix/edit/version info in the title. "
    "The uploader is often NOT the artist (labels, reposts, DJs). Never invent names: "
    "if you cannot tell, use what the title and uploader show and give a low confidence."
)


def ai_parse(tracks: list[Track], api_key: str, model: str = AI_MODEL) -> int:
    """Parse tracks in batches with Claude. Returns how many tracks were updated."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    by_id = {t.id: t for t in tracks}
    updated = 0
    for start in range(0, len(tracks), AI_BATCH_SIZE):
        batch = tracks[start : start + AI_BATCH_SIZE]
        payload = [
            {"id": t.id, "title": t.raw_title, "uploader": t.uploader} for t in batch
        ]
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=_SYSTEM,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "report_tracks"},
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        for block in response.content:
            if block.type != "tool_use":
                continue
            for item in block.input.get("tracks", []):
                track = by_id.get(str(item.get("id")))
                if not track or not item.get("title"):
                    continue
                conf = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
                _apply(track, str(item.get("artist", "")).strip(), item["title"].strip(), conf)
                updated += 1
    return updated


def parse_tracks(tracks: list[Track], api_key: str = "") -> str:
    """Parse all tracks. Uses Claude when a key is set; regex otherwise or on failure.

    Returns a short description of which method was used.
    """
    apply_regex_parse(tracks)  # always set a baseline so every track has a query
    if not api_key:
        return "regex (no ANTHROPIC_API_KEY set)"
    try:
        updated = ai_parse(tracks, api_key)
        return f"Claude ({updated}/{len(tracks)} tracks)"
    except Exception as exc:  # network, auth, rate limit... keep the regex baseline
        return f"regex (AI parsing failed: {type(exc).__name__})"
