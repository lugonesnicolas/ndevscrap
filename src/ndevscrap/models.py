"""Versioned, serializable output models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


@dataclass(frozen=True, slots=True)
class ProductSnapshot:
    """Normalized observation for one sellable SKU."""

    product_id: str
    sku_id: str
    name: str
    brand: str
    categories: tuple[str, ...]
    product_url: str
    image_urls: tuple[str, ...]
    seller_id: str
    seller_name: str
    available: bool
    available_quantity: int
    list_price: Decimal | None
    selling_price: Decimal | None
    currency: str
    postal_code: str
    captured_at: datetime
    source_url: str
    gtin: str | None = None
    promotion: str | None = None
    schema_version: str = "1"

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(frozen=True, slots=True)
class CouponSnapshot:
    """Allowlisted personalized coupon metadata."""

    coupon_id: str
    title: str
    description: str | None
    discount_type: str | None
    discount_value: str | None
    valid_from: str | None
    valid_until: str | None
    conditions: str | None
    applicable_products: tuple[str, ...]
    applicable_categories: tuple[str, ...]
    status: str
    captured_at: datetime
    source_url: str
    schema_version: str = "1"

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(slots=True)
class ComponentResult:
    status: str
    discovered: int = 0
    normalized: int = 0
    rejected: int = 0
    retries: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _json_value(asdict(self))


@dataclass(slots=True)
class RunManifest:
    run_id: str
    snapshot_id: str
    connector_version: str
    store: str
    postal_code: str
    started_at: datetime
    finished_at: datetime
    configuration_hash: str
    status: str
    components: dict[str, ComponentResult]
    duration_seconds: float
    schema_version: str = "1"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return _json_value(data)
