from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path

from .choose import fmt_time, is_snippet, length_difference
from .download import playlist_folder_name
from .fileinfo import read_audio_info
from .models import Track
from .state import Session

LENGTH_WARN_SECONDS = 10
CSV_COLUMNS = [
    "number", "soundcloud_title", "soundcloud_uploader", "soundcloud_length_s", "saved_file", "actual_length_s",
    "length_difference_s", "actual_bitrate_kbps", "bitrate_mode", "sample_rate_hz", "channels", "size_mb",
    "from_user", "remote_path", "reported_bitrate_kbps", "flags",
]


def log_dir_name(playlist_name: str) -> str:
    return re.sub(r"[:/\\]+", "-", playlist_folder_name(playlist_name))


def categorize(track: Track) -> str:
    """Which log section a track belongs in."""
    if track.download_status == "done":
        return "downloaded"
    if track.download_status in ("queued", "failed"):
        return track.download_status
    if track.status == "skipped" and not track.searched:
        return "skipped_terms"
    if not track.searched:
        return "not_searched"
    if not track.matches:
        return "not_found"
    if track.download_status == "skipped":
        return "skipped"
    return "undecided"


def file_flags(track: Track) -> list[str]:
    """Things worth a second look about a downloaded file."""
    info, chosen, flags = track.file_info, track.chosen or {}, []
    if info.get("error"):
        return [info["error"]]
    kbps, length = info.get("bitrate_kbps"), info.get("length")
    if kbps is not None and not 319 <= kbps <= 321:
        flags.append(f"bitrate is {kbps} kbps, not 320")
    if info.get("bitrate_mode") in ("VBR", "ABR"):
        flags.append(f"{info['bitrate_mode']} encoding")
    if info.get("sample_rate") not in (None, 44100):
        flags.append(f"sample rate {info['sample_rate']} Hz")
    if length is not None and track.duration and not is_snippet(track):
        if abs(length - track.duration) > LENGTH_WARN_SECONDS:
            flags.append(f"length differs from SoundCloud by {fmt_time(abs(length - track.duration))}")
    if length is not None and chosen.get("length") and abs(length - chosen["length"]) > 2:
        flags.append("sender reported a different length than the real file")
    return flags


def _fill_file_info(session: Session) -> None:
    """Read details for downloaded files that were saved before details were recorded."""
    changed = False
    for track in session.tracks:
        if track.download_status == "done" and not track.file_info and track.saved_path:
            path = Path(track.saved_path)
            if path.exists():
                track.file_info, changed = read_audio_info(path), True
    if changed:
        session.save()


def _why_not_found(track: Track) -> str:
    stats = track.search_stats
    if not stats:
        return "no search details were recorded"
    if not stats.get("peers"):
        return "no one answered the search"
    seen = ", ".join(f"{count} {label}" for label, count in sorted(stats["formats"].items(), key=lambda x: -x[1]))
    parts = [f"{stats['peers']} peers, {stats['files']} files"]
    parts.append(f"audio seen: {seen}" if seen else "no audio files in the results")
    if stats.get("mp3_320_name_mismatch"):
        parts.append(f"{stats['mp3_320_name_mismatch']} 320 kbps MP3(s) did not match the track name")
    elif not stats["formats"].get("mp3 320"):
        parts.append("none were 320 kbps MP3s")
    return "; ".join(parts)


def _md_cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _downloaded_row(number: int, track: Track) -> dict:
    info, chosen = track.file_info, track.chosen or {}
    length = info.get("length")
    diff = None if length is None or not track.duration else round(length - track.duration, 1)
    return {
        "number": number,
        "soundcloud_title": track.raw_title,
        "soundcloud_uploader": track.uploader,
        "soundcloud_length_s": round(track.duration, 1) if track.duration else "",
        "saved_file": track.saved_path,
        "actual_length_s": round(length, 1) if length else "",
        "length_difference_s": diff if diff is not None else "",
        "actual_bitrate_kbps": info.get("bitrate_kbps") or "",
        "bitrate_mode": info.get("bitrate_mode") or "",
        "sample_rate_hz": info.get("sample_rate") or "",
        "channels": info.get("channels") or "",
        "size_mb": round(info["size_bytes"] / 1_048_576, 2) if info.get("size_bytes") else "",
        "from_user": chosen.get("username", ""),
        "remote_path": chosen.get("filename", ""),
        "reported_bitrate_kbps": chosen.get("bitrate") or "",
        "flags": "; ".join(file_flags(track)),
    }


def write_log(session: Session, out_dir: Path) -> Path:
    """Write the full log (Markdown, CSV and JSON) to <out_dir>/<playlist>/. Returns the Markdown path."""
    _fill_file_info(session)
    folder = out_dir / log_dir_name(session.playlist_name)
    folder.mkdir(parents=True, exist_ok=True)

    groups: dict[str, list[tuple[int, Track]]] = {}
    for number, track in enumerate(session.tracks, start=1):
        groups.setdefault(categorize(track), []).append((number, track))
    count = lambda key: len(groups.get(key, []))  # noqa: E731

    lines = [
        f"# {session.playlist_name}: download log",
        "",
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}. {len(session.tracks)} tracks on SoundCloud.",
        "",
        "| Outcome | Tracks |", "|---|---|",
        f"| Downloaded | {count('downloaded')} |",
        f"| Still queued | {count('queued')} |",
        f"| Download failed | {count('failed')} |",
        f"| Not found (no 320 kbps MP3 match) | {count('not_found')} |",
        f"| Skipped by you (had matches) | {count('skipped')} |",
        f"| Skipped at the search-term step | {count('skipped_terms')} |",
        f"| Found but not decided yet | {count('undecided')} |",
        f"| Not searched yet | {count('not_searched')} |",
        "",
    ]

    rows = [_downloaded_row(n, t) for n, t in groups.get("downloaded", [])]
    lines += ["## Downloaded", ""]
    if rows:
        lines += [
            "| # | SoundCloud track | SC length | File length | Diff | Bitrate | Mode | Sample rate | Size | From | Flags |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for (_, track), row in zip(groups["downloaded"], rows):
            info = track.file_info
            diff_text, _ = length_difference(track.duration, info.get("length"))
            lines.append(
                f"| {row['number']} | {_md_cell(track.raw_title)} | {fmt_time(track.duration)} "
                f"| {fmt_time(info.get('length'))} | {diff_text or '-'} "
                f"| {info.get('bitrate_kbps') or '?'} kbps | {info.get('bitrate_mode') or '?'} "
                f"| {info.get('sample_rate') or '?'} Hz | {row['size_mb'] or '?'} MB "
                f"| {_md_cell(row['from_user'])} | {_md_cell(row['flags']) or 'ok'} |"
            )
        lines += ["", "Saved files:", ""] + [f"- {Path(t.saved_path).name}" for _, t in groups["downloaded"]]
    else:
        lines.append("Nothing downloaded yet.")
    lines.append("")

    def section(title: str, key: str, describe) -> None:
        if not groups.get(key):
            return
        lines.extend([f"## {title}", ""])
        for number, track in groups[key]:
            lines.append(f"- **{number}. {_md_cell(track.raw_title)}** ({_md_cell(track.uploader)}, {fmt_time(track.duration)})")
            for detail in describe(track):
                lines.append(f"  - {detail}")
            if track.url:
                lines.append(f"  - SoundCloud: {track.url}")
        lines.append("")

    def chosen_line(track: Track) -> list[str]:
        chosen = track.chosen or {}
        name = re.split(r"[\\/]", chosen.get("filename", "?"))[-1]
        return [f"chosen: {name} from {chosen.get('username', '?')}"]

    section("Still queued in slskd", "queued", lambda t: chosen_line(t) + ["waiting on the other user; run the same command later to file it"])
    section("Download failed", "failed", lambda t: chosen_line(t) + [f"reason: {t.download_note or 'unknown'}"])
    section("Not found", "not_found", lambda t: [f"searched: {t.query}", f"why: {_why_not_found(t)}"])
    section("Skipped by you", "skipped", lambda t: [f"searched: {t.query}", f"{len(t.matches)} matches were available"])
    section("Skipped at the search-term step", "skipped_terms", lambda t: [])
    section("Found but not decided yet", "undecided", lambda t: [f"searched: {t.query}", f"{len(t.matches)} matches available"])
    section("Not searched yet", "not_searched", lambda t: [f"search term: {t.query}"])

    md_path = folder / "log.md"
    md_path.write_text("\n".join(lines))
    with (folder / "downloaded.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    (folder / "tracks.json").write_text(json.dumps([t.to_dict() for t in session.tracks], indent=2, ensure_ascii=False))
    return md_path
