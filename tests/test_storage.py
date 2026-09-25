from __future__ import annotations

import gzip
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from ndevscrap.contracts import RawRecord
from ndevscrap.models import (
    ComponentResult,
    CouponSnapshot,
    ProductSnapshot,
    RunManifest,
)
from ndevscrap.storage import FileSnapshotStore


def _product(price: str) -> ProductSnapshot:
    return ProductSnapshot(
        product_id="p-1",
        sku_id="sku-1",
        name="Product",
        brand="Brand",
        categories=("/Category/",),
        product_url="https://shop.example/p",
        image_urls=(),
        seller_id="seller",
        seller_name="Seller",
        available=True,
        available_quantity=1,
        list_price=Decimal(10),
        selling_price=Decimal(price),
        currency="ARS",
        postal_code="1000",
        captured_at=datetime(2026, 9, 23, tzinfo=UTC),
        source_url="https://shop.example/api",
    )


def _coupon() -> CouponSnapshot:
    return CouponSnapshot(
        coupon_id="coupon-1",
        title="Coupon",
        description=None,
        discount_type="percentage",
        discount_value="10",
        valid_from=None,
        valid_until=None,
        conditions=None,
        applicable_products=(),
        applicable_categories=(),
        status="available",
        captured_at=datetime(2026, 9, 23, tzinfo=UTC),
        source_url="https://shop.example/coupons",
    )


def _manifest(run_id: str, status: str = "success") -> RunManifest:
    moment = datetime(2026, 9, 23, tzinfo=UTC)
    return RunManifest(
        run_id=run_id,
        snapshot_id="dia:1000:2026-09-23",
        connector_version="1",
        store="dia",
        postal_code="1000",
        started_at=moment,
        finished_at=moment,
        configuration_hash="hash",
        status=status,
        components={
            "catalog": ComponentResult(status="success", normalized=1),
            "clubdia": ComponentResult(status="success", normalized=1),
        },
        duration_seconds=1,
    )


def test_snapshot_replacement_is_idempotent_and_preserves_coupon_current(
    tmp_path: Path,
) -> None:
    first = FileSnapshotStore(
        tmp_path,
        store="dia",
        postal_code="1000",
        snapshot_date=date(2026, 9, 23),
        run_id="run-1",
    )
    first.prepare()
    first.write_raw(
        "catalog",
        RawRecord(
            "page-1",
            "https://shop.example/api",
            {"ok": True},
            datetime(2026, 9, 23, tzinfo=UTC),
        ),
    )
    first.write_products([_product("9")])
    first.write_coupons([_coupon()])
    first.publish(_manifest("run-1"), publish_catalog=True, publish_coupons=True)

    second = FileSnapshotStore(
        tmp_path,
        store="dia",
        postal_code="1000",
        snapshot_date=date(2026, 9, 23),
        run_id="run-2",
    )
    second.prepare()
    second.write_products([_product("8")])
    second.publish(
        _manifest("run-2", "partial_success"),
        publish_catalog=True,
        publish_coupons=False,
    )

    current = tmp_path / "dia" / "1000" / "current"
    assert '"selling_price":"8"' in (current / "products.jsonl").read_text()
    assert '"coupon_id":"coupon-1"' in (current / "coupons.jsonl").read_text()
    assert second.previous_product_count() == 1
    raw = tmp_path / "dia" / "1000" / "2026-09-23" / "raw"
    assert raw.exists()
    assert not any(raw.iterdir())
    assert not list((tmp_path / "dia" / "1000").glob(".*.backup"))


def test_raw_public_payload_is_gzipped(tmp_path: Path) -> None:
    store = FileSnapshotStore(
        tmp_path,
        store="dia",
        postal_code="1000",
        snapshot_date=date(2026, 9, 23),
        run_id="run",
    )
    store.prepare()
    store.write_raw(
        "catalog",
        RawRecord(
            "page-1",
            "https://shop.example/api",
            {"ok": True},
            datetime(2026, 9, 23, tzinfo=UTC),
        ),
    )
    staging = tmp_path / "dia" / "1000" / ".staging-2026-09-23"
    path = next(staging.rglob("*.json.gz"))

    with gzip.open(path, "rt", encoding="utf-8") as handle:
        assert json.load(handle)["payload"] == {"ok": True}
    assert "page-1" in (staging / "checkpoint.json").read_text(encoding="utf-8")


def test_interrupted_staging_can_resume_from_raw_checkpoint(tmp_path: Path) -> None:
    first = FileSnapshotStore(
        tmp_path,
        store="dia",
        postal_code="1000",
        snapshot_date=date(2026, 9, 23),
        run_id="run-1",
    )
    first.prepare()
    record = RawRecord(
        "page-1",
        "https://shop.example/api",
        {"products": []},
        datetime(2026, 9, 23, tzinfo=UTC),
    )
    first.write_raw("catalog", record)

    resumed = FileSnapshotStore(
        tmp_path,
        store="dia",
        postal_code="1000",
        snapshot_date=date(2026, 9, 23),
        run_id="run-2",
    )
    resumed.prepare()

    assert resumed.read_raw("catalog", "page-1") == record
