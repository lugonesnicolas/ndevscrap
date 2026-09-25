"""Store-specific, read-only ClubDIA coupon adapter."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ..contracts import (
    ConnectorMetadata,
    HttpRequest,
    RawRecord,
    RunContext,
    SessionProvider,
    SourceItem,
    Transport,
)
from ..models import CouponSnapshot


class ClubDiaAuthenticationError(RuntimeError):
    """The supplied VTEX session cannot access personalized ClubDIA data."""


class ClubDiaConnector:
    metadata = ConnectorMetadata(
        connector_id="dia-club-coupons",
        version="1.1.0",
        owner="maintainers",
        access_method="authorized-session-api",
        schema_version="1",
    )

    def __init__(
        self, base_url: str, transport: Transport, session: SessionProvider
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._session = session

    def discover(self, context: RunContext) -> Iterable[SourceItem]:
        material = self._session.load()
        yield SourceItem(
            key="clubdia-coupons",
            request=HttpRequest(
                method="GET",
                url=f"{self._base_url}/_v/private/club-dia/_v1/token-by-user",
                headers=material.headers,
                cookies=material.cookies,
            ),
        )

    def extract(self, item: SourceItem, context: RunContext) -> RawRecord:
        token_response = self._transport.request(item.request)
        token = _clubdia_token(token_response.json())
        order_form_id = _header(item.request.headers, "order-form-id")
        if not order_form_id:
            raise ClubDiaAuthenticationError(
                "ClubDIA session is missing the order-form-id captured from the storefront"
            )
        headers = dict(item.request.headers)
        headers.update(
            {
                "Accept": "application/json",
                "clubdia-auth-header": token,
                "order-form-id": order_form_id,
            }
        )
        response = self._transport.request(
            HttpRequest(
                method="GET",
                url=f"{self._base_url}/_v/private/club-dia/_v1/cupons",
                headers=headers,
                cookies=item.request.cookies,
            )
        )
        return RawRecord(
            key=item.key,
            source_url=response.url,
            payload=response.json(),
            fetched_at=datetime.now(UTC),
        )

    def normalize(
        self, record: RawRecord, context: RunContext
    ) -> Iterable[CouponSnapshot]:
        values = _coupon_list(record.payload)
        return tuple(
            _normalize_coupon(value, record.source_url, context)
            for value in values
            if isinstance(value, dict)
        )


def _coupon_list(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        response = payload.get("response")
        if isinstance(response, dict) and isinstance(response.get("cupones"), list):
            return response["cupones"]
        for key in ("coupons", "cupones", "items", "data", "benefits"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    raise ValueError("unexpected ClubDIA coupon payload")


def _normalize_coupon(
    value: Mapping[str, Any], source_url: str, context: RunContext
) -> CouponSnapshot:
    lines = _line_texts(value)
    return CouponSnapshot(
        coupon_id=_required(value, "id", "idCifrado", "couponId", "coupon_id"),
        title=_required(value, "descripcion", "title", "name"),
        description=lines[0] if lines else _optional(value, "description", "summary"),
        discount_type=_optional(
            value,
            "subtipoCupon",
            "tipoCupon",
            "discountType",
            "discount_type",
            "type",
        ),
        discount_value=_optional(value, "discountValue", "discount_value", "value"),
        valid_from=_timestamp(value, "inicioVigencia", "validFrom", "valid_from"),
        valid_until=_timestamp(value, "finVigencia", "validUntil", "valid_until"),
        conditions="\n".join(lines)
        if lines
        else _optional(value, "conditions", "terms"),
        applicable_products=_strings(
            value, "applicableProducts", "applicable_products", "productIds"
        ),
        applicable_categories=_strings(
            value,
            "applicableCategories",
            "applicable_categories",
            "categoryIds",
            "categoria",
        ),
        status=_coupon_status(value),
        captured_at=context.captured_at,
        source_url=_safe_source_url(source_url),
    )


def _clubdia_token(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise ClubDiaAuthenticationError("ClubDIA token response has an invalid schema")
    token = payload.get("tokenClubDia")
    if not isinstance(token, str) or not token:
        raise ClubDiaAuthenticationError(
            "ClubDIA session did not return an authenticated token"
        )
    return token


def _header(headers: Mapping[str, str], name: str) -> str | None:
    expected = name.casefold()
    for key, value in headers.items():
        if key.casefold() == expected and value:
            return value
    return None


def _safe_source_url(value: str) -> str:
    parts = urlsplit(value)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _required(value: Mapping[str, Any], *keys: str) -> str:
    result = _optional(value, *keys)
    if result is None:
        raise ValueError(f"coupon is missing required field {keys[0]}")
    return result


def _optional(value: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        item = value.get(key)
        if isinstance(item, (str, int, float)) and not isinstance(item, bool):
            if item == "":
                continue
            return str(item)
    return None


def _strings(value: Mapping[str, Any], *keys: str) -> tuple[str, ...]:
    for key in keys:
        item = value.get(key)
        if isinstance(item, list):
            return tuple(
                str(entry)
                for entry in item
                if isinstance(entry, (str, int, float))
                and not isinstance(entry, bool)
                and entry != ""
            )
        if isinstance(item, (str, int, float)) and not isinstance(item, bool):
            return (str(item),) if item != "" else ()
    return ()


def _line_texts(value: Mapping[str, Any]) -> tuple[str, ...]:
    lines = value.get("lineas")
    if not isinstance(lines, list):
        return ()
    return tuple(
        text.strip()
        for line in lines
        if isinstance(line, dict)
        and isinstance((text := line.get("texto")), str)
        and text.strip()
    )


def _timestamp(value: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        item = value.get(key)
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            seconds = (
                float(item) / 1000
                if abs(float(item)) >= 10_000_000_000
                else float(item)
            )
            try:
                return datetime.fromtimestamp(seconds, tz=UTC).isoformat()
            except (OSError, OverflowError, ValueError):
                return str(item)
        if isinstance(item, str) and item:
            return item
    return None


def _coupon_status(value: Mapping[str, Any]) -> str:
    if value.get("usado") is True:
        return "used"
    if value.get("futuro") is True:
        return "future"
    if value.get("aceptableEnListado") is True:
        return "available"
    return _optional(value, "status", "state") or "unavailable"
