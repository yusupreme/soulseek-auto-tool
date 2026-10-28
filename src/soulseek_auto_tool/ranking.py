from __future__ import annotations

import re

AUDIO_EXTENSIONS = {
    "mp3", "flac", "wav", "aiff", "aif", "m4a", "aac", "ogg", "opus", "alac", "wv",
}
LOSSLESS = {"flac", "wav", "aiff", "aif", "alac", "wv"}
MIN_NAME_MATCH = 0.5


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _basename(path: str) -> str:
    return re.split(r"[\\/]", path)[-1]


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _quality_points(ext: str, bitrate: int | None) -> float:
    if ext in LOSSLESS:
        return 40
    if ext == "mp3":
        if bitrate is None:
            return 15
        if bitrate >= 320:
            return 35
        if bitrate >= 256:
            return 28
        if bitrate >= 192:
            return 18
        return 8
    return 20


def score_file(
    file: dict, response: dict, query: str, duration: float | None
) -> tuple[float, dict] | None:
    """Score one file from a peer's response. Returns None if it isn't a good match."""
    filename = file.get("filename", "")
    ext = (file.get("extension") or _extension(filename)).lower().lstrip(".")
    if ext not in AUDIO_EXTENSIONS:
        return None

    query_tokens = _tokens(query)
    if not query_tokens:
        return None
    overlap = len(query_tokens & _tokens(_basename(filename) + " " + filename)) / len(query_tokens)
    if overlap < MIN_NAME_MATCH:
        return None

    score = overlap * 40 + _quality_points(ext, file.get("bitRate"))
    free_slot = bool(response.get("hasFreeUploadSlot"))
    queue = int(response.get("queueLength") or 0)
    speed = float(response.get("uploadSpeed") or 0)
    score += 15 if free_slot else 0
    score -= min(queue, 50) * 0.3
    score += min(speed / 500_000, 5)

    length = file.get("length")
    if duration and length:
        diff = abs(duration - length)
        score += 15 if diff <= 3 else (-15 if diff > 10 else 0)

    return score, {
        "username": response.get("username", ""),
        "filename": filename,
        "size": file.get("size"),
        "extension": ext,
        "bitrate": file.get("bitRate"),
        "length": length,
        "free_slot": free_slot,
        "queue_length": queue,
        "upload_speed": speed,
        "score": round(score, 1),
    }


def rank_responses(
    responses: list[dict], query: str, duration: float | None = None, limit: int = 5
) -> list[dict]:
    """Return the best `limit` matches across all peer responses, best first."""
    scored: list[tuple[float, dict]] = []
    for response in responses:
        for file in response.get("files", []):
            result = score_file(file, response, query, duration)
            if result:
                scored.append(result)
    scored.sort(key=lambda item: item[0], reverse=True)
    return [match for _, match in scored[:limit]]
