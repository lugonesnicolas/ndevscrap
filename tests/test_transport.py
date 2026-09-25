from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from ndevscrap.contracts import HttpRequest
from ndevscrap.transport import HttpStatusError, RequestsTransport


@dataclass
class FakeResponse:
    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    content: bytes = b"{}"
    url: str = "https://shop.example/api"


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.headers: dict[str, str] = {}

    def request(self, **kwargs):
        return self.responses.pop(0)


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        self.value += 1.0
        return self.value


def test_transport_respects_retry_after() -> None:
    sleeps: list[float] = []
    session = FakeSession([FakeResponse(429, {"Retry-After": "2"}), FakeResponse(200)])
    transport = RequestsTransport(
        timeout_seconds=1,
        requests_per_second=1,
        max_retries=3,
        user_agent="test",
        session=session,
        sleep=sleeps.append,
        monotonic=Clock(),
        jitter=lambda: 0,
    )

    response = transport.request(HttpRequest("GET", "https://shop.example/api"))

    assert response.status_code == 200
    assert transport.retries == 1
    assert 2.0 in sleeps


def test_transport_does_not_retry_authentication_errors() -> None:
    session = FakeSession([FakeResponse(401)])
    transport = RequestsTransport(
        timeout_seconds=1,
        requests_per_second=1,
        max_retries=3,
        user_agent="test",
        session=session,
        monotonic=Clock(),
    )

    with pytest.raises(HttpStatusError) as error:
        transport.request(HttpRequest("GET", "https://shop.example/api"))

    assert error.value.status_code == 401
    assert transport.retries == 0
