"""Rate-limited requests transport with bounded retries."""

from __future__ import annotations

import math
import random
import time
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from http.cookiejar import Cookie, DefaultCookiePolicy
from urllib.parse import urljoin

import requests
from urllib3.util import parse_url

from . import __version__
from .config import HttpSettings
from .contracts import HttpRequest, HttpResponse, TransportStats

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
MAX_REDIRECTS = 5
_BUILD_ERRORS = (
    requests.exceptions.InvalidHeader,
    requests.exceptions.InvalidURL,
    requests.exceptions.MissingSchema,
    requests.exceptions.InvalidSchema,
    UnicodeError,
)


class TransportError(RuntimeError):
    """Base error for HTTP acquisition."""


class HttpStatusError(TransportError):
    def __init__(self, status_code: int, url: str) -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(f"HTTP {status_code} for {url}")


class RequestBuildError(TransportError):
    """The request cannot be built; retrying would never succeed."""


class UnexpectedRedirectError(TransportError):
    """A public request was redirected outside its HTTPS origin."""


class _RejectResponseCookies(DefaultCookiePolicy):
    """Only cookies passed explicitly with a request are ever sent."""

    def set_ok(self, cookie: Cookie, request: object) -> bool:
        return False


class RequestsTransport:
    """Synchronous transport suitable for conservative storefront access.

    Requests that carry cookies or headers never follow redirects. Public
    requests follow at most ``MAX_REDIRECTS`` redirects within their HTTPS
    origin. Response cookies are never stored, and errors never keep the
    original exception, which may hold session material, as cause or context.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float,
        requests_per_second: float,
        max_retries: int,
        user_agent: str,
        max_retry_after_seconds: float = 120.0,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] = random.random,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._minimum_interval = 1.0 / requests_per_second
        self._max_retries = max_retries
        self._max_retry_after_seconds = max_retry_after_seconds
        self._session = session or requests.Session()
        self._session.trust_env = False
        self._session.cookies.set_policy(_RejectResponseCookies())
        self._session.headers.update(
            {"User-Agent": user_agent, "Accept": "application/json"}
        )
        self._sleep = sleep
        self._monotonic = monotonic
        self._jitter = jitter
        self._wall_clock = wall_clock
        self._last_request_at: float | None = None
        self._requests = 0
        self._retries = 0
        self._status_counts: dict[int, int] = {}

    def stats(self) -> TransportStats:
        return TransportStats(
            requests=self._requests,
            retries=self._retries,
            status_counts=self._status_counts,
        )

    def request(self, request: HttpRequest) -> HttpResponse:
        for attempt in range(self._max_retries + 1):
            response = self._send(request)
            if isinstance(response, str):
                if attempt >= self._max_retries:
                    raise TransportError(
                        f"HTTP request failed after retries: {response}"
                    )
                self._retry(attempt, None)
                continue
            if (
                response.status_code in RETRYABLE_STATUS_CODES
                and attempt < self._max_retries
            ):
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

    def _send(self, request: HttpRequest) -> requests.Response | str:
        """Send one attempt, following allowed redirects.

        A network error is returned as its type name so that the caller waits
        outside any ``except`` block.
        """
        carries_session = bool(request.cookies or request.headers)
        url = request.url
        params: dict[str, str | int | bool] | None = dict(request.params)
        for hop in range(MAX_REDIRECTS + 1):
            response = self._send_once(request, url, params)
            if (
                isinstance(response, str)
                or response.status_code not in REDIRECT_STATUS_CODES
                or carries_session
            ):
                return response
            location = response.headers.get("Location")
            target = urljoin(response.url, location) if location else None
            if hop == MAX_REDIRECTS or target is None:
                raise UnexpectedRedirectError("public redirect was not followed")
            prepared = _prepared_same_origin(request.url, target)
            if prepared is None:
                raise UnexpectedRedirectError("public redirect left the origin")
            url, params = prepared, None
        raise AssertionError("redirect loop exhausted without returning or raising")

    def _send_once(
        self,
        request: HttpRequest,
        url: str,
        params: dict[str, str | int | bool] | None,
    ) -> requests.Response | str:
        self._wait_for_rate_limit()
        self._requests += 1
        self._session.cookies.clear()
        build_failed = False
        network_error = ""
        try:
            response = self._session.request(
                method=request.method,
                url=url,
                params=params,
                headers=dict(request.headers),
                cookies=dict(request.cookies),
                timeout=self._timeout_seconds,
                allow_redirects=False,
            )
        except _BUILD_ERRORS:
            build_failed = True
        except requests.RequestException as exc:
            network_error = type(exc).__name__
        finally:
            self._session.cookies.clear()
        # Raised outside the except blocks: the original error may contain
        # header values and must not become the cause or context.
        if build_failed:
            raise RequestBuildError("HTTP request could not be built")
        if network_error:
            return network_error
        self._status_counts[response.status_code] = (
            self._status_counts.get(response.status_code, 0) + 1
        )
        return response

    def _wait_for_rate_limit(self) -> None:
        now = self._monotonic()
        if self._last_request_at is not None:
            remaining = self._minimum_interval - (now - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._monotonic()

    def _retry(self, attempt: int, retry_after: str | None) -> None:
        delay = _retry_after_seconds(retry_after, self._wall_clock)
        if delay is not None and delay > self._max_retry_after_seconds:
            raise TransportError("Retry-After exceeds the configured maximum")
        if delay is None:
            delay = (0.5 * (2**attempt)) + (self._jitter() * 0.25)
        self._retries += 1
        self._sleep(delay)


def build_transport(http: HttpSettings, contact: str | None) -> RequestsTransport:
    user_agent = f"NDevScrap/{__version__}"
    if contact:
        user_agent = f"{user_agent} (+{contact})"
    return RequestsTransport(
        timeout_seconds=http.timeout_seconds,
        requests_per_second=http.requests_per_second,
        max_retries=http.max_retries,
        max_retry_after_seconds=http.max_retry_after_seconds,
        user_agent=user_agent,
    )


def https_origin(url: str) -> tuple[str, int] | None:
    """Return the HTTPS host and port as the sending stack parses ``url``.

    URLs with credentials, backslashes or control characters are refused
    because parsers disagree on where their authority ends.
    """
    if "\\" in url or any(ord(char) < 0x21 or ord(char) == 0x7F for char in url):
        return None
    try:
        parts = parse_url(requests.Request("GET", url).prepare().url or "")
    except (requests.RequestException, ValueError):
        return None
    if parts.scheme != "https" or not parts.host or parts.auth is not None:
        return None
    return parts.host.lower(), parts.port or 443


def _prepared_same_origin(original: str, target: str) -> str | None:
    destination = https_origin(target)
    if destination is None or destination != https_origin(original):
        return None
    return requests.Request("GET", target).prepare().url


def _retry_after_seconds(
    value: str | None, wall_clock: Callable[[], float]
) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        seconds = retry_at.timestamp() - wall_clock()
        return max(0.0, seconds)
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return seconds
