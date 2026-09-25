from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ndevscrap.connectors.clubdia import (
    ClubDiaAuthenticationError,
    ClubDiaConnector,
)
from ndevscrap.contracts import (
    HttpResponse,
    RawRecord,
    RunContext,
    SessionMaterial,
)

FIXTURE = Path(__file__).parent / "fixtures" / "clubdia" / "coupons.json"


class FakeSessionProvider:
    def load(self) -> SessionMaterial:
        return SessionMaterial(
            headers={"order-form-id": "order-form-secret"},
            cookies={"vtex_session": "cookie-secret"},
        )


class FakeTransport:
    retries = 0

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.requests = []

    def request(self, request):
        self.requests.append(request)
        if len(self.requests) == 1:
            body = json.dumps({"tokenClubDia": "token-secret"}).encode()
        else:
            body = json.dumps(self.payload).encode()
        return HttpResponse(200, request.url, {}, body)


def test_coupon_acquisition_uses_ephemeral_token_and_order_form() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    transport = FakeTransport(payload)
    connector = ClubDiaConnector(
        "https://shop.example", transport, FakeSessionProvider()
    )
    context = RunContext("run", "dia", "1806", datetime(2026, 9, 25, tzinfo=UTC))

    item = next(iter(connector.discover(context)))
    record = connector.extract(item, context)

    assert len(transport.requests) == 2
    assert transport.requests[0].url.endswith("/token-by-user")
    coupon_request = transport.requests[1]
    assert coupon_request.method == "GET"
    assert coupon_request.url.endswith("/cupons")
    assert coupon_request.headers["clubdia-auth-header"] == "token-secret"
    assert coupon_request.headers["order-form-id"] == "order-form-secret"
    assert "token-secret" not in record.source_url


def test_coupon_acquisition_requires_order_form_id() -> None:
    class MissingOrderFormSession:
        def load(self) -> SessionMaterial:
            return SessionMaterial(headers={}, cookies={"vtex_session": "secret"})

    connector = ClubDiaConnector(
        "https://shop.example",
        FakeTransport({}),
        MissingOrderFormSession(),
    )
    context = RunContext("run", "dia", "1806", datetime(2026, 9, 25, tzinfo=UTC))

    item = next(iter(connector.discover(context)))

    try:
        connector.extract(item, context)
    except ClubDiaAuthenticationError as exc:
        assert "order-form-id" in str(exc)
    else:
        raise AssertionError("missing order-form-id was accepted")


def test_coupon_normalization_uses_allowlist() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    captured = datetime(2026, 9, 23, 12, tzinfo=UTC)
    connector = object.__new__(ClubDiaConnector)
    record = RawRecord(
        key="clubdia-coupons",
        source_url="https://shop.example/_v/private/club-dia/_v1/cupons",
        payload=payload,
        fetched_at=captured,
    )

    coupons = tuple(
        connector.normalize(
            record,
            RunContext("run", "dia", "1000", captured),
        )
    )

    assert len(coupons) == 1
    data = coupons[0].to_dict()
    assert data["coupon_id"] == "101"
    assert data["title"] == "Cupón sanitizado"
    assert data["discount_type"] == "porcentaje"
    assert data["valid_from"] == "2026-08-31T23:00:00+00:00"
    assert data["valid_until"] == "2026-09-30T23:59:59+00:00"
    assert data["conditions"] == "10% de descuento\nCondición sanitizada"
    assert data["applicable_categories"] == ["7"]
    assert data["status"] == "available"
    assert data["source_url"].endswith("/_v/private/club-dia/_v1/cupons")
    assert "customerEmail" not in data
    assert "document" not in data
    assert "secret" not in json.dumps(data)
