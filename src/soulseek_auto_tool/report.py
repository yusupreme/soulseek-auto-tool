from __future__ import annotations

import json
from pathlib import Path

from .state import Session


def _size_mb(size: int | None) -> str:
    return f"{size / 1_048_576:.1f} MB" if size else "?"


def write_report(session: Session, out_dir: Path) -> tuple[Path, Path]:
    """Write a Markdown report and a JSON file. Returns (markdown_path, json_path)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = session.path.stem
    md_path, json_path = out_dir / f"{stem}.md", out_dir / f"{stem}.json"

    searched = [t for t in session.tracks if t.searched]
    found = [t for t in searched if t.matches]
    lines = [
        f"# {session.playlist_name}",
        "",
        f"{len(found)} of {len(searched)} searched tracks have matches.",
        "",
    ]
    for track in searched:
        lines.append(f"## {track.query}")
        if not track.matches:
            lines += ["No matches found.", ""]
            continue
        lines += ["| # | User | File | Format | Size | Free slot | Queue |", "|---|---|---|---|---|---|---|"]
        for i, m in enumerate(track.matches, start=1):
            name = m["filename"].replace("\\", "/").split("/")[-1].replace("|", "\\|")
            fmt = m["extension"] + (f" {m['bitrate']}k" if m.get("bitrate") else "")
            lines.append(
                f"| {i} | {m['username']} | {name} | {fmt} | {_size_mb(m.get('size'))} "
                f"| {'yes' if m['free_slot'] else 'no'} | {m['queue_length']} |"
            )
        lines.append("")

    md_path.write_text("\n".join(lines))
    json_path.write_text(json.dumps([t.to_dict() for t in session.tracks], indent=2, ensure_ascii=False))
    return md_path, json_path
