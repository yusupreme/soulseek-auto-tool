from __future__ import annotations

import time
import uuid
from typing import Callable
from urllib.parse import quote

import httpx


class SlskdError(RuntimeError):
    pass


class SlskdClient:
    """Minimal client for the slskd REST API (https://github.com/slskd/slskd)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url,
            headers={"X-API-Key": api_key},
            timeout=30,
            transport=transport,
        )
        self._sleep = sleep

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise SlskdError(f"Cannot reach slskd: {exc}") from exc
        if response.status_code in (401, 403):
            raise SlskdError("slskd rejected the API key (check SLSKD_API_KEY).")
        if response.status_code >= 400:
            raise SlskdError(f"slskd returned {response.status_code} for {method} {path}")
        return response

    def check(self) -> None:
        """Raise SlskdError unless slskd is reachable and the key works."""
        self._request("GET", "/api/v0/application")

    def start_search(self, text: str) -> str:
        search_id = str(uuid.uuid4())
        self._request("POST", "/api/v0/searches", json={"id": search_id, "searchText": text})
        return search_id

    def wait_for_search(self, search_id: str, timeout: float = 30, poll: float = 1.5) -> bool:
        """Poll until the search completes. Returns False if it timed out."""
        waited = 0.0
        while waited <= timeout:
            state = self._request("GET", f"/api/v0/searches/{search_id}").json().get("state", "")
            if "Completed" in state:
                return True
            self._sleep(poll)
            waited += poll
        return False

    def get_responses(self, search_id: str) -> list[dict]:
        return self._request("GET", f"/api/v0/searches/{search_id}/responses").json()

    def delete_search(self, search_id: str) -> None:
        self._request("DELETE", f"/api/v0/searches/{search_id}")

    def queue_download(self, username: str, files: list[dict]) -> None:
        """Ask slskd to download files ({"filename", "size"}) from a peer."""
        self._request("POST", f"/api/v0/transfers/downloads/{quote(username, safe='')}", json=files)

    def list_downloads(self, username: str) -> list[dict]:
        """All download transfers with one peer, flattened to a list of file dicts."""
        data = self._request("GET", f"/api/v0/transfers/downloads/{quote(username, safe='')}").json()
        return [f for d in data.get("directories", []) for f in d.get("files", [])]
