from __future__ import annotations

import re

# A file only counts as a match if this share of the search words appear in its path.
MIN_NAME_MATCH = 0.7

# How many matches to keep per track (the review screen shows them 5 at a time).
RESULT_LIMIT = 20


def _tokens(text: str) -> set[str]:
    # [^\W_]+ splits on underscores too, so "tribe_vibes" becomes "tribe" and "vibes".
    return set(re.findall(r"[^\W_]+", text.lower()))


# Words that rarely appear in file names, so they don't count against a match.
OPTIONAL_WORDS = {"original", "mix"}


def _required_tokens(query: str) -> set[str]:
    tokens = _tokens(query)
    return (tokens - OPTIONAL_WORDS) or tokens


def name_overlap(filename: str, query: str) -> float:
    """Share of the query's words that appear in the file's path (1.0 = all of them)."""
    needed = _required_tokens(query)
    return len(needed & _tokens(filename)) / len(needed) if needed else 0.0


def _basename(path: str) -> str:
    return re.split(r"[\\/]", path)[-1]


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def is_320_mp3(ext: str, bitrate: int | None) -> bool:
    """Only 320 kbps MP3s are accepted. Files with an unknown bitrate are rejected."""
    return ext == "mp3" and bitrate is not None and bitrate >= 320


def score_file(file: dict, response: dict, query: str) -> tuple[tuple, dict] | None:
    """Sort key and details for one file, or None if it isn't a match for the query."""
    filename = file.get("filename", "")
    ext = (file.get("extension") or _extension(filename)).lower().lstrip(".")
    bitrate = file.get("bitRate")
    if not is_320_mp3(ext, bitrate):
        return None

    query_tokens = _required_tokens(query)
    if not query_tokens:
        return None
    overlap = len(query_tokens & _tokens(filename)) / len(query_tokens)
    if overlap < MIN_NAME_MATCH:
        return None

    size = int(file.get("size") or 0)
    free_slot = bool(response.get("hasFreeUploadSlot"))
    queue = int(response.get("queueLength") or 0)

    # Best first: the largest file, then (only to break ties) a free slot and a short queue.
    key = (-size, not free_slot, queue)
    return key, {
        "username": response.get("username", ""),
        "filename": filename,
        "size": size,
        "extension": ext,
        "bitrate": bitrate,
        "length": file.get("length"),
        "free_slot": free_slot,
        "queue_length": queue,
        "upload_speed": float(response.get("uploadSpeed") or 0),
    }


def summarize_responses(responses: list[dict], query: str) -> dict:
    """Describe what a search returned, to explain an empty result later."""
    formats: dict[str, int] = {}
    files = mp3_320_name_mismatch = 0
    needed = _required_tokens(query)
    for response in responses:
        for file in response.get("files", []):
            files += 1
            filename = file.get("filename", "")
            ext = (file.get("extension") or _extension(filename)).lower().lstrip(".")
            if ext == "mp3":
                bitrate = file.get("bitRate")
                label = "mp3 320" if is_320_mp3(ext, bitrate) else "mp3 other"
                if label == "mp3 320" and needed and len(needed & _tokens(filename)) / len(needed) < MIN_NAME_MATCH:
                    mp3_320_name_mismatch += 1
            elif ext in {"flac", "wav", "aiff", "aif", "m4a", "ogg", "opus", "aac", "alac", "wv"}:
                label = ext
            else:
                continue  # images, playlists, nfo files...
            formats[label] = formats.get(label, 0) + 1
    return {
        "peers": len(responses),
        "files": files,
        "formats": formats,
        "mp3_320_name_mismatch": mp3_320_name_mismatch,
    }


def rank_responses(responses: list[dict], query: str, limit: int = RESULT_LIMIT) -> list[dict]:
    """Return the best `limit` matches across all peer responses, best first."""
    scored: list[tuple[tuple, dict]] = []
    for response in responses:
        for file in response.get("files", []):
            result = score_file(file, response, query)
            if result:
                scored.append(result)
    scored.sort(key=lambda item: item[0])
    return [match for _, match in scored[:limit]]
