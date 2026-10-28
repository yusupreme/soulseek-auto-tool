from __future__ import annotations

from typing import Callable

from .models import Track
from .pacer import Pacer
from .ranking import rank_responses
from .slskd import SlskdClient
from .state import Session


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
        client.wait_for_search(search_id, timeout=search_timeout)
        responses = client.get_responses(search_id)
        track.matches = rank_responses(responses, track.query, track.duration)
        track.searched = True
        client.delete_search(search_id)
        session.save()
