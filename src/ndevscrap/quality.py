"""Quality gates applied before publishing current data."""

from __future__ import annotations

from dataclasses import dataclass

from .models import ProductSnapshot


@dataclass(frozen=True, slots=True)
class QualityResult:
    products: tuple[ProductSnapshot, ...]
    rejected: int
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def evaluate_products(
    products: list[ProductSnapshot], previous_count: int | None
) -> QualityResult:
    unique: dict[tuple[str, str], ProductSnapshot] = {}
    rejected = 0
    for product in products:
        if not _valid(product):
            rejected += 1
            continue
        unique[(product.sku_id, product.seller_id)] = product

    valid = tuple(unique.values())
    attempted = len(products)
    errors: list[str] = []
    if not valid:
        errors.append("catalog contains zero valid products")
    if attempted and (rejected / attempted) > 0.05:
        errors.append(f"invalid product ratio {rejected}/{attempted} exceeds 5 percent")
    if previous_count and len(valid) < previous_count * 0.70:
        errors.append(
            f"product count {len(valid)} dropped more than 30 percent "
            f"from {previous_count}"
        )
    return QualityResult(products=valid, rejected=rejected, errors=tuple(errors))


def _valid(product: ProductSnapshot) -> bool:
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
