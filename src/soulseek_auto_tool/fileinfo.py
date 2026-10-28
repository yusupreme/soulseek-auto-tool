from __future__ import annotations

from pathlib import Path


# mutagen's BitrateMode values; UNKNOWN (0) is left as None
_BITRATE_MODES = {1: "CBR", 2: "VBR", 3: "ABR"}


def read_audio_info(path: Path) -> dict:
    """Read the real properties of a downloaded audio file (not what the sender claimed)."""
    info: dict = {"size_bytes": path.stat().st_size}
    try:
        import mutagen

        audio = mutagen.File(path, easy=True)
    except Exception:
        audio = None
    if audio is None or getattr(audio, "info", None) is None:
        info["error"] = "could not read audio properties"
        return info

    props = audio.info
    bitrate = getattr(props, "bitrate", None)
    mode = getattr(props, "bitrate_mode", None)
    info.update(
        length=getattr(props, "length", None),
        bitrate_kbps=round(bitrate / 1000) if bitrate else None,
        bitrate_mode=_BITRATE_MODES.get(int(mode)) if mode is not None else None,  # CBR / VBR / ABR
        sample_rate=getattr(props, "sample_rate", None),
        channels=getattr(props, "channels", None),
    )
    tags = getattr(audio, "tags", None) or {}
    for key in ("artist", "title"):
        value = tags.get(key)
        if value:
            info[f"tag_{key}"] = str(value[0])
    return info


def quality_problem(info: dict) -> str | None:
    """Why a downloaded file is not a genuine 320 kbps CBR MP3, or None if it is (or cannot be judged).

    A file whose properties could not be read is not judged here; the log flags it instead.
    """
    if info.get("error"):
        return None
    kbps, mode = info.get("bitrate_kbps"), info.get("bitrate_mode")
    if kbps is not None and not 319 <= kbps <= 321:
        return f"real bitrate is {kbps} kbps"
    if mode in ("VBR", "ABR"):
        return f"{mode} encoding ({kbps} kbps average)" if kbps else f"{mode} encoding"
    return None
