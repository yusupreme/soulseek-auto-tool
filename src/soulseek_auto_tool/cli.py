from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.markup import escape

from .config import load_settings
from .choose import choose_matches
from .download import playlist_folder_name, run_downloads
from .pacer import Pacer
from .parser import parse_tracks
from .playlist import fetch_playlist
from .report import write_report
from .review import review_tracks
from .search import run_searches, search_one
from .slskd import SlskdClient, SlskdError
from .state import Session, session_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slsk-auto",
        description="Pull tracks from a SoundCloud playlist, review the search terms, "
        "then search them on Soulseek (via slskd) at a gentle pace.",
    )
    parser.add_argument("playlist_url", help="Public SoundCloud playlist URL")
    parser.add_argument("--no-ai", action="store_true", help="Skip Claude, use regex parsing only")
    parser.add_argument("--retry-empty", action="store_true", help="Search again for saved tracks that found no matches")
    parser.add_argument("--min-delay", type=float, default=3.0, help="Min seconds between searches")
    parser.add_argument("--max-delay", type=float, default=4.5, help="Max seconds between searches")
    parser.add_argument("--search-only", action="store_true", help="Only search and write the report; skip choosing and downloading")
    parser.add_argument("--wait", type=float, default=10, help="Minutes to wait for downloads (default 10)")
    parser.add_argument("--library-dir", type=Path, help="Where playlist folders are saved (default: LIBRARY_DIR)")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="Where progress is saved")
    parser.add_argument("--output-dir", type=Path, default=Path("output"), help="Where reports go")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    console = Console()
    settings = load_settings()
    args.library_dir = (args.library_dir or settings.library_dir).expanduser()

    if not settings.slskd_api_key:
        console.print("[red]SLSKD_API_KEY is not set.[/red] Copy .env.example to .env and fill it in.")
        return 1

    client = SlskdClient(settings.slskd_url, settings.slskd_api_key)
    try:
        client.check()
    except SlskdError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    path = session_path(args.data_dir, args.playlist_url)
    if path.exists():
        session = Session.load(path)
        console.print(f"Resuming saved session: [bold]{escape(session.playlist_name)}[/bold]")
        if args.retry_empty:
            console.print(f"Searching again for {session.reset_empty()} track(s) that found nothing.")
    else:
        console.print("Fetching playlist...")
        name, tracks = fetch_playlist(args.playlist_url)
        session = Session(path=path, playlist_url=args.playlist_url, playlist_name=name, tracks=tracks)
        method = parse_tracks(tracks, "" if args.no_ai else settings.anthropic_api_key)
        console.print(f"Found {len(tracks)} tracks. Parsed with {method}.")
        session.save()

    if not review_tracks(session, console):
        console.print("\nProgress saved. Run the same command again to continue.")
        return 0

    accepted = sum(1 for t in session.tracks if t.status == "accepted" and not t.searched)
    console.print(f"\nSearching {accepted} tracks, one every {args.min_delay}-{args.max_delay}s...")
    pacer = Pacer(args.min_delay, args.max_delay)
    try:
        run_searches(
            session,
            client,
            pacer,
            on_progress=lambda i, n, t: console.print(f"[dim]{i}/{n}[/dim] searching: {escape(t.query)}"),
            on_fallback=lambda old, new: console.print(f"[dim]nothing for[/dim] {escape(old)}[dim], retrying as[/dim] {escape(new)}"),
        )
        md_path, _ = write_report(session, args.output_dir)
        console.print(f"\n[green]Searches done.[/green] Report: {md_path}")

        if not args.search_only:
            console.print("\nNow review each track: compare SoundCloud with what Soulseek found.")
            if not choose_matches(session, console, retry=lambda t: search_one(t, client, pacer)):
                console.print("\nProgress saved. Run the same command again to continue.")
                return 0
            folder = args.library_dir / playlist_folder_name(session.playlist_name)
            console.print(f"\nDownloading into: {folder}")
            run_downloads(
                session,
                client,
                settings.slskd_downloads_dir,
                args.library_dir,
                wait=args.wait * 60,
                on_event=lambda message: console.print(f"  {message}"),
            )
            left = sum(1 for t in session.tracks if t.download_status == "queued")
            if left:
                console.print(
                    f"[yellow]{left} file(s) are still queued in slskd.[/yellow] "
                    "Run the same command later to file them."
                )
    except SlskdError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    except KeyboardInterrupt:
        session.save()
        console.print("\nStopped. Progress saved.")
        return 130
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
