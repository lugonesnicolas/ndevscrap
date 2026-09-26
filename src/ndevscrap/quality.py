"""Quality gates applied before publishing current data."""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from .models import ProductSnapshot


@dataclass(frozen=True, slots=True)
class QualityPolicy:
    """Thresholds for a critical component, evaluated with integer arithmetic."""

    min_valid: int = 1
    max_invalid_percent: int = 5
    max_drop_percent: int = 30


class QualityGate:
    """Filter rows in streaming while counting rejected and duplicated ones."""

    def __init__(
        self,
        *,
        validator: Callable[[Any], bool] | None = None,
        record_key: Callable[[Any], Hashable] | None = None,
    ) -> None:
        self._validator = validator
        self._record_key = record_key
        self._seen: set[Hashable] = set()
        self.discovered = 0
        self.rejected = 0
        self.duplicates = 0

    def filter(self, rows: Iterable[Any]) -> Iterator[Any]:
        for row in rows:
            self.discovered += 1
            if self._validator is not None and not self._validator(row):
                self.rejected += 1
                continue
            if self._record_key is not None:
                key = self._record_key(row)
                if key in self._seen:
                    self.duplicates += 1
                    continue
                self._seen.add(key)
            yield row


def evaluate_counts(
    policy: QualityPolicy,
    *,
    valid: int,
    discovered: int,
    rejected: int,
    baseline: int | None,
) -> tuple[str, ...]:
    errors: list[str] = []
    if valid < policy.min_valid:
        errors.append(
            "catalog contains zero valid products"
            if valid == 0
            else f"catalog contains {valid} valid products, below {policy.min_valid}"
        )
    if discovered and rejected * 100 > discovered * policy.max_invalid_percent:
        errors.append(
            f"invalid product ratio {rejected}/{discovered} exceeds "
            f"{policy.max_invalid_percent} percent"
        )
    if baseline and valid * 100 < baseline * (100 - policy.max_drop_percent):
        errors.append(
            f"product count {valid} dropped more than "
            f"{policy.max_drop_percent} percent from {baseline}"
        )
    return tuple(errors)


def valid_product(product: ProductSnapshot) -> bool:
    if not all(
        (
            product.product_id,
            product.sku_id,
            product.name,
            product.seller_id,
            product.source_url,
            product.currency,
            product.postal_code,
        )
    ):
        return False
    if product.available and product.selling_price is None:
        return False
    return product.available_quantity >= 0
