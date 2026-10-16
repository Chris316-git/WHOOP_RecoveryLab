"""Thin WHOOP v2 API client with automatic token refresh, pagination and rate-limit backoff."""
import time
from datetime import datetime
from typing import Iterator

import httpx

from src import config
from src.ingestion import whoop_auth


class WhoopClient:
    PAGE_SIZE = 25  # maximum allowed by the API
    MAX_RETRIES = 5

    def __init__(self, user_id: str, store):  # FileTokenStore or DbTokenStore
        self.user_id = user_id
        self.store = store
        self.token = store.load(user_id)

    def _refresh(self) -> None:
        self.token = whoop_auth.refresh(self.token)
        self.store.save(self.user_id, self.token)

    def _get(self, path: str, params: dict | None = None) -> dict:
        if self.token.is_expired:
            self._refresh()
        url = f"{config.WHOOP_API_BASE}{path}"
        refreshed = False
        for attempt in range(self.MAX_RETRIES):
            headers = {"Authorization": f"Bearer {self.token.access_token}"}
            response = httpx.get(url, headers=headers, params=params, timeout=30)
            if response.status_code == 401 and not refreshed:
                self._refresh()
                refreshed = True
                continue
            if response.status_code == 429 or response.status_code >= 500:
                time.sleep(2 ** attempt)  # exponential backoff
                continue
            response.raise_for_status()
            return response.json()
        response.raise_for_status()
        return response.json()

    def _paginate(self, path: str, start: datetime | None = None, end: datetime | None = None) -> Iterator[dict]:
        params: dict = {"limit": self.PAGE_SIZE}
        if start:
            params["start"] = start.isoformat()
        if end:
            params["end"] = end.isoformat()
        while True:
            page = self._get(path, params)
            yield from page.get("records", [])
            next_token = page.get("next_token")
            if not next_token:
                break
            params["nextToken"] = next_token

    def profile(self) -> dict:
        return self._get("/user/profile/basic")

    def body_measurement(self) -> dict:
        return self._get("/user/measurement/body")

    def recoveries(self, start=None, end=None) -> Iterator[dict]:
        return self._paginate("/recovery", start, end)

    def sleeps(self, start=None, end=None) -> Iterator[dict]:
        return self._paginate("/activity/sleep", start, end)

    def cycles(self, start=None, end=None) -> Iterator[dict]:
        return self._paginate("/cycle", start, end)

    def workouts(self, start=None, end=None) -> Iterator[dict]:
        return self._paginate("/activity/workout", start, end)
