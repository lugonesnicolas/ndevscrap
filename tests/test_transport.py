from __future__ import annotations

import io
import sys
import traceback
from collections.abc import Callable
from email.utils import formatdate
from http.client import HTTPMessage
from http.cookiejar import CookieJar
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from requests.adapters import BaseAdapter, HTTPAdapter
from requests.cookies import extract_cookies_to_jar
from urllib3 import HTTPResponse

from ndevscrap.config import HttpSettings
from ndevscrap.contracts import HttpRequest
from ndevscrap.transport import (
    HttpStatusError,
    RequestBuildError,
    RequestsTransport,
    TransportError,
    UnexpectedRedirectError,
    build_transport,
)

URL = "https://shop.example/api"
SENTINEL = "SENTINEL-secret-value"

Reply = tuple[int, list[tuple[str, str]]]
Handler = Callable[[requests.PreparedRequest], "Reply | BaseException"]


def _raw_response(status: int, headers: list[tuple[str, str]]) -> HTTPResponse:
    """Build a urllib3 response that requests processes like a real one."""
    message = HTTPMessage()
    for name, value in headers:
        message[name] = value
    original = SimpleNamespace(msg=message, isclosed=lambda: False, close=lambda: None)
    return HTTPResponse(
        body=io.BytesIO(b"{}"),
        headers=list(headers),
        status=status,
        preload_content=False,
        original_response=original,
    )


class FakeAdapter(BaseAdapter):
    def __init__(self, handler: Handler) -> None:
        super().__init__()
        self.handler = handler
        self.sent: list[requests.PreparedRequest] = []
        self.timeouts: list[object] = []

    def send(self, request, **kwargs):
        self.sent.append(request)
        self.timeouts.append(kwargs.get("timeout"))
        reply = self.handler(request)
        if isinstance(reply, BaseException):
            raise reply
        status, headers = reply
        return HTTPAdapter().build_response(request, _raw_response(status, headers))

    def close(self) -> None:
        pass


def _replies(*replies: Reply | BaseException) -> Handler:
    queue = list(replies)
    return lambda request: queue.pop(0) if len(queue) > 1 else queue[0]


def _session(handler: Handler) -> tuple[requests.Session, FakeAdapter]:
    session = requests.Session()
    adapter = FakeAdapter(handler)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session, adapter


class Clock:
    """Monotonic clock advanced only by the injected sleep."""

    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        assert sys.exc_info() == (None, None, None), "slept with an active exception"
        self.sleeps.append(seconds)
        self.value += seconds


def _transport(
    handler: Handler,
    *,
    max_retries: int = 3,
    requests_per_second: float = 1000.0,
    max_retry_after_seconds: float = 120.0,
    jitter: float = 0.0,
    wall_clock: Callable[[], float] = lambda: 0.0,
) -> tuple[RequestsTransport, FakeAdapter, Clock]:
    session, adapter = _session(handler)
    clock = Clock()
    transport = RequestsTransport(
        timeout_seconds=1,
        requests_per_second=requests_per_second,
        max_retries=max_retries,
        max_retry_after_seconds=max_retry_after_seconds,
        user_agent="test",
        session=session,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        jitter=lambda: jitter,
        wall_clock=wall_clock,
    )
    return transport, adapter, clock


def _public(url: str = URL) -> HttpRequest:
    return HttpRequest("GET", url)


def _with_session(url: str = URL) -> HttpRequest:
    return HttpRequest(
        "GET",
        url,
        headers={"order-form-id": SENTINEL},
        cookies={"vtex_session": SENTINEL},
    )


def test_transport_respects_retry_after() -> None:
    transport, _, clock = _transport(_replies((429, [("Retry-After", "2")]), (200, [])))

    response = transport.request(_public())

    assert response.status_code == 200
    assert transport.stats().retries == 1
    assert 2.0 in clock.sleeps


def test_transport_does_not_retry_authentication_errors() -> None:
    transport, adapter, _ = _transport(_replies((401, [])))

    with pytest.raises(HttpStatusError) as error:
        transport.request(_public())

    assert error.value.status_code == 401
    assert transport.stats().retries == 0
    assert len(adapter.sent) == 1


def test_backoff_is_exponential_with_jitter() -> None:
    transport, _, clock = _transport(
        _replies((503, []), (503, []), (200, [])), jitter=0.5
    )

    response = transport.request(_public())

    assert response.status_code == 200
    assert clock.sleeps == [0.625, 1.125]
    assert transport.stats().retries == 2


def test_retryable_status_is_raised_when_retries_are_exhausted() -> None:
    transport, adapter, _ = _transport(_replies((503, [])), max_retries=2)

    with pytest.raises(HttpStatusError) as error:
        transport.request(_public())

    assert error.value.status_code == 503
    assert len(adapter.sent) == 3
    assert transport.stats().retries == 2


@pytest.mark.parametrize(
    "failure",
    [requests.Timeout("slow"), requests.ConnectionError("reset")],
)
def test_network_errors_are_retried(failure: BaseException) -> None:
    transport, adapter, clock = _transport(_replies(failure, (200, [])))

    response = transport.request(_public())

    assert response.status_code == 200
    assert len(adapter.sent) == 2
    assert clock.sleeps == [0.5]


def test_exhausted_network_errors_keep_no_context() -> None:
    transport, adapter, clock = _transport(
        _replies(requests.ConnectionError(f"reset {SENTINEL}")), max_retries=2
    )

    with pytest.raises(TransportError) as error:
        transport.request(_with_session())

    assert str(error.value) == "HTTP request failed after retries: ConnectionError"
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert SENTINEL not in "".join(traceback.format_exception(error.value))
    assert len(adapter.sent) == 3
    assert len(clock.sleeps) == 2


def test_rate_limit_spaces_consecutive_requests() -> None:
    transport, _, clock = _transport(_replies((200, [])), requests_per_second=2)

    transport.request(_public())
    transport.request(_public())

    assert clock.sleeps == [0.5]


def test_retry_after_http_date_uses_the_wall_clock() -> None:
    header = formatdate(1_010, usegmt=True)
    transport, _, clock = _transport(
        _replies((503, [("Retry-After", header)]), (200, [])),
        wall_clock=lambda: 1_000.0,
    )

    transport.request(_public())

    assert clock.sleeps == [10.0]


@pytest.mark.parametrize("value", ["nan", "-5", "inf"])
def test_invalid_retry_after_falls_back_to_backoff(value: str) -> None:
    transport, _, clock = _transport(
        _replies((429, [("Retry-After", value)]), (200, []))
    )

    transport.request(_public())

    assert clock.sleeps == [0.5]


def test_retry_after_above_the_cap_stops_without_waiting() -> None:
    transport, adapter, clock = _transport(
        _replies((429, [("Retry-After", "500")]), (200, [])),
        max_retry_after_seconds=120,
    )

    with pytest.raises(TransportError) as error:
        transport.request(_public())

    assert not isinstance(error.value, HttpStatusError)
    assert str(error.value) == "Retry-After exceeds the configured maximum"
    assert clock.sleeps == []
    assert len(adapter.sent) == 1
    assert transport.stats().retries == 0


def test_retry_after_above_the_cap_on_the_last_attempt_keeps_the_status() -> None:
    transport, _, clock = _transport(
        _replies((429, [("Retry-After", "500")])), max_retries=0
    )

    with pytest.raises(HttpStatusError) as error:
        transport.request(_public())

    assert error.value.status_code == 429
    assert clock.sleeps == []


@pytest.mark.parametrize(
    ("url", "headers"),
    [
        (URL, {"order-form-id": f"bad\n{SENTINEL}"}),
        (f"shop.example/{SENTINEL}", {}),
        (f"ftp://shop.example/{SENTINEL}", {}),
        (f"https://shop.example:{SENTINEL}/api", {}),
    ],
    ids=["InvalidHeader", "MissingSchema", "InvalidSchema", "InvalidURL"],
)
def test_request_build_errors_are_not_retried_and_keep_no_context(
    url: str, headers: dict[str, str]
) -> None:
    transport, adapter, clock = _transport(_replies((200, [])))

    with pytest.raises(RequestBuildError) as error:
        transport.request(HttpRequest("GET", url, headers=headers))

    assert str(error.value) == "HTTP request could not be built"
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert SENTINEL not in "".join(traceback.format_exception(error.value))
    assert adapter.sent == []
    assert clock.sleeps == []
    assert transport.stats().retries == 0


def test_header_encoding_errors_are_request_build_errors() -> None:
    # http.client raises this while sending a non latin-1 header; the fake
    # adapter raises it to exercise the same path without a socket.
    failure = UnicodeEncodeError("latin-1", f"{SENTINEL}’", 21, 22, "ordinal")
    transport, adapter, clock = _transport(_replies(failure))

    with pytest.raises(RequestBuildError) as error:
        transport.request(_with_session())

    assert error.value.__context__ is None
    assert SENTINEL not in "".join(traceback.format_exception(error.value))
    assert len(adapter.sent) == 1
    assert clock.sleeps == []


@pytest.mark.parametrize(
    "location", ["https://shop.example/login", "https://evil.example/login"]
)
def test_requests_with_session_material_never_follow_redirects(location: str) -> None:
    transport, adapter, _ = _transport(_replies((302, [("Location", location)])))

    with pytest.raises(HttpStatusError) as error:
        transport.request(_with_session())

    assert error.value.status_code == 302
    assert len(adapter.sent) == 1
    assert transport.stats().retries == 0


def test_public_redirect_to_the_same_origin_is_followed() -> None:
    transport, adapter, _ = _transport(
        _replies(
            (301, [("Location", "/api/v2")]),
            (302, [("Location", "https://shop.example/api/v3")]),
            (200, []),
        )
    )

    response = transport.request(_public())

    assert response.status_code == 200
    assert [request.url for request in adapter.sent] == [
        URL,
        "https://shop.example/api/v2",
        "https://shop.example/api/v3",
    ]
    stats = transport.stats()
    assert stats.requests == 3
    assert dict(stats.status_counts) == {301: 1, 302: 1, 200: 1}


@pytest.mark.parametrize(
    "headers",
    [
        [("Location", "https://evil.example/api")],
        [("Location", "http://shop.example/api")],
        [("Location", "https://shop.example:8443/api")],
        [("Location", "https://evil.example\\@shop.example/api")],
        [("Location", "https://user:pass@shop.example/api")],
        [],
    ],
    ids=[
        "other-host",
        "plain-http",
        "other-port",
        "backslash-authority",
        "userinfo",
        "no-location",
    ],
)
def test_public_redirect_outside_the_origin_is_rejected_before_sending(
    headers: list[tuple[str, str]],
) -> None:
    transport, adapter, clock = _transport(_replies((302, headers), (200, [])))

    with pytest.raises(UnexpectedRedirectError):
        transport.request(_public())

    assert [request.url for request in adapter.sent] == [URL]
    assert clock.sleeps == []


def test_public_redirect_chain_is_bounded() -> None:
    transport, adapter, _ = _transport(_replies((302, [("Location", URL)])))

    with pytest.raises(UnexpectedRedirectError):
        transport.request(_public())

    assert len(adapter.sent) == 6


def test_harness_control_plain_session_keeps_response_cookies() -> None:
    session, adapter = _session(_replies((200, [("Set-Cookie", "rotated=x; Path=/")])))

    session.get(URL)
    session.get(URL)

    assert session.cookies.get("rotated") == "x"
    assert adapter.sent[1].headers.get("Cookie") == "rotated=x"


def test_response_cookies_are_neither_kept_nor_sent() -> None:
    transport, adapter, _ = _transport(
        _replies((200, [("Set-Cookie", f"rotated={SENTINEL}; Path=/")]))
    )

    transport.request(_with_session())
    transport.request(_public())

    assert adapter.sent[0].headers["Cookie"] == f"vtex_session={SENTINEL}"
    assert "Cookie" not in adapter.sent[1].headers
    assert len(transport._session.cookies) == 0


def test_cookie_policy_rejects_response_cookies() -> None:
    transport, _, _ = _transport(_replies((200, [])))
    prepared = requests.Request("GET", URL).prepare()
    raw = _raw_response(200, [("Set-Cookie", "rotated=x; Path=/")])
    control = CookieJar()

    extract_cookies_to_jar(transport._session.cookies, prepared, raw)
    extract_cookies_to_jar(control, prepared, raw)

    assert len(transport._session.cookies) == 0
    assert len(control) == 1


def test_cookie_jar_is_cleared_around_each_request() -> None:
    transport, adapter, _ = _transport(_replies((200, [])))
    transport._session.cookies.set("planted", SENTINEL, domain="shop.example")

    transport.request(_public())

    assert "Cookie" not in adapter.sent[0].headers
    assert len(transport._session.cookies) == 0


def test_environment_credentials_are_not_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    netrc = tmp_path / "netrc"
    netrc.write_text(f"machine shop.example login user password {SENTINEL}\n")
    monkeypatch.setenv("NETRC", str(netrc))
    control_session, control_adapter = _session(_replies((200, [])))
    transport, adapter, _ = _transport(_replies((200, [])))

    control_session.get(URL)
    transport.request(_public())

    assert "Authorization" in control_adapter.sent[0].headers
    assert "Authorization" not in adapter.sent[0].headers


def test_stats_count_attempts_retries_and_status_codes() -> None:
    transport, _, _ = _transport(_replies((503, []), (200, [])))

    transport.request(_public())
    stats = transport.stats()

    assert (stats.requests, stats.retries) == (2, 1)
    assert dict(stats.status_counts) == {503: 1, 200: 1}
    with pytest.raises(TypeError):
        stats.status_counts[200] = 5  # type: ignore[index]
    assert stats.since(stats).requests == 0


def test_build_transport_uses_settings_and_contact_user_agent() -> None:
    transport = build_transport(HttpSettings(), "ops@example.com")
    _, adapter = _session(_replies((200, [])))
    transport._session.mount("https://", adapter)

    transport.request(_public())

    assert adapter.sent[0].headers["User-Agent"] == "NDevScrap/0.1.0 (+ops@example.com)"
    assert transport._session.trust_env is False


def test_public_redirect_host_comparison_ignores_case_and_default_port() -> None:
    transport, adapter, _ = _transport(
        _replies((302, [("Location", "https://SHOP.example:443/api/v2")]), (200, []))
    )

    transport.request(_public())

    assert len(adapter.sent) == 2


def test_build_transport_applies_every_http_setting() -> None:
    settings = HttpSettings(
        timeout_seconds=30,
        requests_per_second=0.5,
        max_retries=2,
        max_retry_after_seconds=60,
    )
    transport = build_transport(settings, None)
    _, adapter = _session(
        _replies(
            (503, [("Retry-After", "1")]), (503, [("Retry-After", "1")]), (503, [])
        )
    )
    transport._session.mount("https://", adapter)
    clock = Clock()
    transport._sleep = clock.sleep
    transport._monotonic = clock.monotonic

    with pytest.raises(HttpStatusError):
        transport.request(_public())

    assert adapter.timeouts == [30, 30, 30]
    assert len(adapter.sent) == 3
    assert clock.sleeps == [1.0, 1.0, 1.0, 1.0]
    assert adapter.sent[0].headers["User-Agent"] == "NDevScrap/0.1.0"

    capped = build_transport(settings, None)
    _, capped_adapter = _session(_replies((429, [("Retry-After", "61")])))
    capped._session.mount("https://", capped_adapter)
    with pytest.raises(TransportError, match="Retry-After exceeds"):
        capped.request(_public())
