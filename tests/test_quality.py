from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from ndevscrap.models import ProductSnapshot
from ndevscrap.quality import (
    QualityGate,
    QualityPolicy,
    evaluate_counts,
    valid_product,
)


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


def _catalog_gate() -> QualityGate:
    return QualityGate(
        validator=valid_product,
        record_key=lambda product: (product.sku_id, product.seller_id),
    )


def _evaluate(
    products: list[ProductSnapshot], baseline: int | None
) -> tuple[tuple[str, ...], list[ProductSnapshot], QualityGate]:
    gate = _catalog_gate()
    kept = list(gate.filter(products))
    errors = evaluate_counts(
        QualityPolicy(),
        valid=len(kept),
        discovered=gate.discovered,
        rejected=gate.rejected,
        baseline=baseline,
    )
    return errors, kept, gate


def test_quality_rejects_more_than_five_percent_invalid() -> None:
    products = [_product(index) for index in range(19)] + [_product(20, name="")]

    errors, _, _ = _evaluate(products, baseline=None)

    assert not errors
    products.append(_product(21, name=""))
    errors, _, _ = _evaluate(products, baseline=None)
    assert errors
    assert "exceeds 5 percent" in errors[0]
    assert errors[0] == "invalid product ratio 2/21 exceeds 5 percent"


def test_quality_rejects_large_volume_drop() -> None:
    errors, _, _ = _evaluate([_product(index) for index in range(6)], baseline=10)

    assert errors
    assert "dropped more than 30 percent" in errors[0]
    assert errors[0] == "product count 6 dropped more than 30 percent from 10"


def test_quality_accepts_a_drop_of_exactly_thirty_percent() -> None:
    errors, _, _ = _evaluate([_product(index) for index in range(7)], baseline=10)

    assert errors == ()


def test_quality_rejects_zero_products() -> None:
    errors, _, _ = _evaluate([], baseline=None)

    assert errors == ("catalog contains zero valid products",)


def test_quality_skips_the_drop_check_without_a_positive_baseline() -> None:
    for baseline in (None, 0):
        errors, _, _ = _evaluate([_product(1)], baseline=baseline)
        assert errors == ()


def test_gate_keeps_the_first_duplicate_and_counts_every_row() -> None:
    first = _product(1)
    duplicate = replace(first, selling_price=Decimal("1.00"))
    invalid = _product(2, name="")

    errors, kept, gate = _evaluate([first, _product(3), duplicate, invalid], None)

    assert errors == ("invalid product ratio 1/4 exceeds 5 percent",)
    assert kept == [first, _product(3)]
    assert (gate.discovered, gate.rejected, gate.duplicates) == (4, 1, 1)
    assert gate.discovered == len(kept) + gate.rejected + gate.duplicates


def test_gate_without_validator_or_key_only_counts() -> None:
    gate = QualityGate()

    rows = list(gate.filter(["a", "a", "b"]))

    assert rows == ["a", "a", "b"]
    assert (gate.discovered, gate.rejected, gate.duplicates) == (3, 0, 0)


def test_policy_percentages_drive_the_messages() -> None:
    errors = evaluate_counts(
        QualityPolicy(max_invalid_percent=10, max_drop_percent=50),
        valid=4,
        discovered=10,
        rejected=2,
        baseline=10,
    )

    assert errors == (
        "invalid product ratio 2/10 exceeds 10 percent",
        "product count 4 dropped more than 50 percent from 10",
    )


def test_invalid_ratio_boundary_is_exact() -> None:
    policy = QualityPolicy()

    assert (
        evaluate_counts(policy, valid=19, discovered=20, rejected=1, baseline=None)
        == ()
    )
    assert evaluate_counts(
        policy, valid=18, discovered=19, rejected=1, baseline=None
    ) == ("invalid product ratio 1/19 exceeds 5 percent",)


def test_drop_boundary_is_exact() -> None:
    policy = QualityPolicy()

    assert (
        evaluate_counts(policy, valid=70, discovered=70, rejected=0, baseline=100) == ()
    )
    assert evaluate_counts(
        policy, valid=69, discovered=69, rejected=0, baseline=100
    ) == ("product count 69 dropped more than 30 percent from 100",)
