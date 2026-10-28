from __future__ import annotations

from typing import Callable

from .models import Track
from .pacer import Pacer
from .ranking import rank_responses
from .slskd import SlskdClient
from .state import Session


def collect_results(track: Track, client: SlskdClient, search_id: str, search_timeout: float = 30) -> None:
    """Wait for a started search to finish, then store its ranked matches on the track."""
    client.wait_for_search(search_id, timeout=search_timeout)
    track.matches = rank_responses(client.get_responses(search_id), track.query)
    track.searched = True
    client.delete_search(search_id)


def search_one(track: Track, client: SlskdClient, pacer: Pacer, search_timeout: float = 30) -> None:
    """Search a single track (used when the user edits a search term during review)."""
    pacer.wait()
    collect_results(track, client, client.start_search(track.query), search_timeout)


def run_searches(
    session: Session,
    client: SlskdClient,
    pacer: Pacer,
    on_progress: Callable[[int, int, Track], None] | None = None,
    search_timeout: float = 30,
) -> None:
    """Search every accepted, not-yet-searched track, one every few seconds.

    Searches are started on the Pacer's schedule; results are collected after.
    Progress is saved after each track, so an interrupted run can be resumed.
    """
    todo = [t for t in session.tracks if t.status == "accepted" and not t.searched]
    started: list[tuple[Track, str]] = []

    for index, track in enumerate(todo, start=1):
        pacer.wait()
        started.append((track, client.start_search(track.query)))
        if on_progress:
            on_progress(index, len(todo), track)

    for track, search_id in started:
        collect_results(track, client, search_id, search_timeout)
        session.save()
