from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from ndevscrap.models import ProductSnapshot
from ndevscrap.quality import evaluate_products


def _product(index: int, *, name: str = "Product") -> ProductSnapshot:
    return ProductSnapshot(
        product_id=f"p-{index}",
        sku_id=f"sku-{index}",
        name=name,
        brand="Brand",
        categories=("/Category/",),
        product_url="https://shop.example/product/p",
        image_urls=(),
        seller_id="seller",
        seller_name="Seller",
        available=True,
        available_quantity=1,
        list_price=Decimal("10.00"),
        selling_price=Decimal("9.00"),
        currency="ARS",
        postal_code="1000",
        captured_at=datetime(2026, 9, 23, tzinfo=UTC),
        source_url="https://shop.example/api",
    )


def test_quality_rejects_more_than_five_percent_invalid() -> None:
    products = [_product(index) for index in range(19)] + [_product(20, name="")]

    result = evaluate_products(products, previous_count=None)

    assert result.ok
    products.append(_product(21, name=""))
    result = evaluate_products(products, previous_count=None)
    assert not result.ok
    assert "exceeds 5 percent" in result.errors[0]


def test_quality_rejects_large_volume_drop() -> None:
    result = evaluate_products(
        [_product(index) for index in range(6)], previous_count=10
    )

    assert not result.ok
    assert "dropped more than 30 percent" in result.errors[0]


def test_quality_rejects_zero_products() -> None:
    result = evaluate_products([], previous_count=None)

    assert not result.ok
    assert result.errors == ("catalog contains zero valid products",)
