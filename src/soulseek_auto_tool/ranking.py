from __future__ import annotations

import re

# A file only counts as a match if this share of the search words appear in its path.
MIN_NAME_MATCH = 0.7


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


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

    query_tokens = _tokens(query)
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


def rank_responses(responses: list[dict], query: str, limit: int = 5) -> list[dict]:
    """Return the best `limit` matches across all peer responses, best first."""
    scored: list[tuple[tuple, dict]] = []
    for response in responses:
        for file in response.get("files", []):
            result = score_file(file, response, query)
            if result:
                scored.append(result)
    scored.sort(key=lambda item: item[0])
    return [match for _, match in scored[:limit]]
