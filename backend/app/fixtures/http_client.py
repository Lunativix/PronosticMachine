"""Retry, exponential backoff, and a simple rate limit. Secrets are never logged."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

import httpx

LOGGER = logging.getLogger(__name__)


class HttpGiveUp(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def request_with_retry(
    send: Callable[[], httpx.Response],
    *,
    attempts: int = 4,
    base_delay: float = 0.4,
    sleeper: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    last_error = "request failed"
    status: int | None = None
    for attempt in range(attempts):
        try:
            response = send()
        except httpx.HTTPError as exc:
            last_error = type(exc).__name__
            status = None
        else:
            if response.status_code not in {429, 500, 502, 503, 504}:
                return response
            status = response.status_code
            last_error = f"HTTP {status}"
        if attempt == attempts - 1:
            break
        sleeper(base_delay * (2**attempt))
    raise HttpGiveUp(last_error, status)


class RateLimiter:
    def __init__(self, min_interval: float = 0.2, sleeper: Callable[[float], None] = time.sleep) -> None:
        self.min_interval = min_interval
        self.sleeper = sleeper
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self, now: Callable[[], float] = time.monotonic) -> None:
        with self._lock:
            current = now()
            gap = self.min_interval - (current - self._last)
            if gap > 0:
                self.sleeper(gap)
                current = now()
            self._last = current
