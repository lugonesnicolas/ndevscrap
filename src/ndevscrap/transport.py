"""Rate-limited requests transport with bounded retries."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from email.utils import parsedate_to_datetime

import requests

from .contracts import HttpRequest, HttpResponse


class TransportError(RuntimeError):
    """Base error for HTTP acquisition."""


class HttpStatusError(TransportError):
    def __init__(self, status_code: int, url: str) -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(f"HTTP {status_code} for {url}")


class RequestsTransport:
    """Synchronous transport suitable for conservative storefront access."""

    _RETRYABLE = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        timeout_seconds: float,
        requests_per_second: float,
        max_retries: int,
        user_agent: str,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._minimum_interval = 1.0 / requests_per_second
        self._max_retries = max_retries
        self._session = session or requests.Session()
        self._session.headers.update(
            {"User-Agent": user_agent, "Accept": "application/json"}
        )
        self._sleep = sleep
        self._monotonic = monotonic
        self._jitter = jitter
        self._last_request_at: float | None = None
        self.retries = 0

    def request(self, request: HttpRequest) -> HttpResponse:
        for attempt in range(self._max_retries + 1):
            self._wait_for_rate_limit()
            try:
                response = self._session.request(
                    method=request.method,
                    url=request.url,
                    params=dict(request.params),
                    headers=dict(request.headers),
                    cookies=dict(request.cookies),
                    timeout=self._timeout_seconds,
                )
            except requests.RequestException as exc:
                if attempt >= self._max_retries:
                    raise TransportError("HTTP request failed after retries") from exc
                self._retry(attempt, None)
                continue

            if response.status_code in self._RETRYABLE and attempt < self._max_retries:
                self._retry(attempt, response.headers.get("Retry-After"))
                continue
            if not 200 <= response.status_code < 300:
                raise HttpStatusError(response.status_code, response.url)
            return HttpResponse(
                status_code=response.status_code,
                url=response.url,
                headers=dict(response.headers),
                body=response.content,
            )
        raise AssertionError("retry loop exhausted without returning or raising")

    def _wait_for_rate_limit(self) -> None:
        now = self._monotonic()
        if self._last_request_at is not None:
            remaining = self._minimum_interval - (now - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._monotonic()

    def _retry(self, attempt: int, retry_after: str | None) -> None:
        self.retries += 1
        delay = _retry_after_seconds(retry_after)
        if delay is None:
            delay = (0.5 * (2**attempt)) + (self._jitter() * 0.25)
        self._sleep(max(0.0, delay))


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            return max(0.0, retry_at.timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            return None
