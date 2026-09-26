from __future__ import annotations

import gzip
import hashlib
import json
import os
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from ndevscrap import storage
from ndevscrap.contracts import RawRecord
from ndevscrap.models import (
    ComponentResult,
    CouponSnapshot,
    ProductSnapshot,
    RunManifest,
)
from ndevscrap.storage import FileSnapshotStore

SNAPSHOT_DATE = date(2026, 9, 23)


def _product(price: str, sku: str = "sku-1") -> ProductSnapshot:
    return ProductSnapshot(
        product_id="p-1",
        sku_id=sku,
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


def _store(root: Path, run_id: str) -> FileSnapshotStore:
    store = FileSnapshotStore(
        root,
        store="dia",
        postal_code="1000",
        snapshot_date=SNAPSHOT_DATE,
        run_id=run_id,
    )
    store.prepare()
    return store


def _record(key: str, payload: object | None = None) -> RawRecord:
    return RawRecord(
        key,
        "https://shop.example/api",
        {"ok": True} if payload is None else payload,
        datetime(2026, 9, 23, tzinfo=UTC),
    )


def _location(root: Path) -> Path:
    return root / "dia" / "1000"


def _index(root: Path) -> dict:
    path = _location(root) / "current" / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        digest.update(path.relative_to(root).as_posix().encode())
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _legacy_current(root: Path, *, rows: int, manifest_status: str) -> None:
    current = _location(root) / "current"
    current.mkdir(parents=True)
    (current / "products.jsonl").write_text("{}\n" * rows, encoding="utf-8")
    legacy = _manifest("legacy-run", manifest_status).to_dict()
    legacy["components"]["catalog"]["status"] = "quality_failure"
    (current / "manifest.json").write_text(json.dumps(legacy), encoding="utf-8")


def test_snapshot_replacement_is_idempotent_and_preserves_coupon_current(
    tmp_path: Path,
) -> None:
    first = _store(tmp_path, "run-1")
    first.write_raw("catalog", _record("page-1"))
    first.write_products([_product("9")])
    first.write_coupons([_coupon()])
    first.publish(_manifest("run-1"), catalog_outcome="accepted", publish_coupons=True)

    second = _store(tmp_path, "run-2")
    second.write_products([_product("8")])
    second.publish(
        _manifest("run-2", "partial_success"),
        catalog_outcome="accepted",
        publish_coupons=False,
    )

    location = _location(tmp_path)
    current = location / "current"
    assert '"selling_price":"8"' in (current / "products.jsonl").read_text()
    assert '"coupon_id":"coupon-1"' in (current / "coupons.jsonl").read_text()
    assert second.previous_product_count() == 1
    raw = location / "2026-09-23" / "raw"
    assert raw.exists()
    assert not any(raw.iterdir())
    assert (location / "attempts" / "2026-09-23" / "run-1" / "raw").exists()
    assert not list(location.glob(".*.backup"))


def test_raw_public_payload_is_gzipped_atomically(tmp_path: Path) -> None:
    store = _store(tmp_path, "run")
    store.write_raw("catalog", _record("page-1"))
    staging = _location(tmp_path) / ".staging-2026-09-23"
    path = next(staging.rglob("*.json.gz"))

    with gzip.open(path, "rt", encoding="utf-8") as handle:
        assert json.load(handle)["payload"] == {"ok": True}
    assert "page-1" in (staging / "checkpoint.json").read_text(encoding="utf-8")
    assert not list(staging.rglob("*.tmp"))


def test_interrupted_staging_can_resume_from_raw_checkpoint(tmp_path: Path) -> None:
    first = _store(tmp_path, "run-1")
    record = _record("page-1", {"products": []})
    first.write_raw("catalog", record)

    resumed = _store(tmp_path, "run-2")

    assert resumed.read_raw("catalog", "page-1") == record


def test_unreadable_raw_is_treated_as_missing(tmp_path: Path) -> None:
    store = _store(tmp_path, "run")
    store.write_raw("catalog", _record("page-1"))
    path = next((_location(tmp_path) / ".staging-2026-09-23").rglob("*.json.gz"))
    path.write_bytes(path.read_bytes()[:10])

    assert store.read_raw("catalog", "page-1") is None


def test_rejected_pages_are_never_read_for_resume(tmp_path: Path) -> None:
    store = _store(tmp_path, "run")
    store.write_rejected("catalog", _record("page-3", {"unexpected": True}))

    staging = _location(tmp_path) / ".staging-2026-09-23"
    assert (staging / "rejected" / "catalog" / "page-3.json.gz").exists()
    assert store.read_raw("catalog", "page-3") is None


def test_resume_clears_everything_but_confirmed_raw(tmp_path: Path) -> None:
    first = _store(tmp_path, "run-1")
    first.write_raw("catalog", _record("page-1"))
    first.write_rejected("catalog", _record("page-2"))
    first.write_coupons([_coupon()])
    staging = _location(tmp_path) / ".staging-2026-09-23"
    (staging / "raw" / "catalog" / "page-3.json.gz.tmp").write_bytes(b"partial")

    _store(tmp_path, "run-2")

    assert sorted(path.name for path in staging.iterdir()) == [
        "checkpoint.json",
        "normalized",
        "raw",
    ]
    assert not any((staging / "normalized").iterdir())
    assert [path.name for path in (staging / "raw" / "catalog").iterdir()] == [
        "page-1.json.gz"
    ]


def test_baseline_comes_from_current_index(tmp_path: Path) -> None:
    store = _store(tmp_path, "run-1")
    store.write_products([_product("9", "sku-1"), _product("9", "sku-2")])
    store.publish(_manifest("run-1"), catalog_outcome="accepted", publish_coupons=False)

    index = _index(tmp_path)
    assert index["kind"] == "current-index"
    assert index["components"]["catalog"]["records"] == 2
    assert index["components"]["catalog"]["normalized"] == 2
    assert _store(tmp_path, "run-2").previous_product_count() == 2


def test_legacy_manifest_of_failed_attempt_uses_published_rows(tmp_path: Path) -> None:
    _legacy_current(tmp_path, rows=3, manifest_status="failed")

    store = _store(tmp_path, "run-1")

    assert store.previous_product_count() == 3
    store.write_products([])
    store.publish(
        _manifest("run-1", "failed"),
        catalog_outcome="quarantined",
        publish_coupons=False,
    )
    catalog = _index(tmp_path)["components"]["catalog"]
    assert catalog["provenance"] == "legacy"
    assert catalog["run_id"] is None
    assert catalog["source"] is None
    assert catalog["records"] == 3


@pytest.mark.parametrize("content", ["{not json", json.dumps({"kind": "other"})])
def test_corrupt_or_foreign_index_falls_back_to_row_count(
    tmp_path: Path, content: str
) -> None:
    current = _location(tmp_path) / "current"
    current.mkdir(parents=True)
    (current / "products.jsonl").write_text("{}\n{}\n", encoding="utf-8")
    (current / "manifest.json").write_text(content, encoding="utf-8")

    assert _store(tmp_path, "run").previous_product_count() == 2


def test_index_without_catalog_entry_counts_published_rows(tmp_path: Path) -> None:
    current = _location(tmp_path) / "current"
    current.mkdir(parents=True)
    (current / "products.jsonl").write_text("{}\n", encoding="utf-8")
    (current / "manifest.json").write_text(
        json.dumps({"kind": "current-index", "index_version": "1", "components": {}}),
        encoding="utf-8",
    )

    assert _store(tmp_path, "run").previous_product_count() == 1


def test_first_run_has_no_baseline(tmp_path: Path) -> None:
    assert _store(tmp_path, "run").previous_product_count() is None


@pytest.mark.parametrize("locked_prefix", [".staging-", ".current-"])
def test_failed_promotion_restores_snapshot_and_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, locked_prefix: str
) -> None:
    first = _store(tmp_path, "run-1")
    first.write_products([_product("9")])
    first.write_coupons([_coupon()])
    first.publish(_manifest("run-1"), catalog_outcome="accepted", publish_coupons=True)
    location = _location(tmp_path).resolve()
    snapshot = _tree_hash(location / "2026-09-23")
    current = _tree_hash(location / "current")

    second = _store(tmp_path, "run-2")
    second.write_products([_product("8")])
    real_replace = os.replace

    def locked(source, destination) -> None:
        if Path(source).name.startswith(locked_prefix):
            raise PermissionError("directory is locked")
        real_replace(source, destination)

    monkeypatch.setattr(storage.os, "replace", locked)

    with pytest.raises(PermissionError):
        second.publish(
            _manifest("run-2"), catalog_outcome="accepted", publish_coupons=False
        )

    monkeypatch.setattr(storage.os, "replace", real_replace)
    assert _tree_hash(location / "2026-09-23") == snapshot
    assert _tree_hash(location / "current") == current
    assert not (location / "attempts" / "2026-09-23" / "run-1").exists()
    assert not list(location.glob(".current-*"))
    assert (location / ".staging-2026-09-23" / "normalized" / "products.jsonl").exists()


def test_raw_with_a_colliding_file_name_is_not_reused(tmp_path: Path) -> None:
    store = _store(tmp_path, "run")
    store.write_raw("catalog", _record("a/b-c:page-001"))

    assert store.read_raw("catalog", "a-b/c:page-001") is None
    assert store.read_raw("catalog", "a/b-c:page-001") is not None


@pytest.mark.parametrize("content", ["not json", json.dumps({"run_id": "..."})])
def test_unidentifiable_previous_snapshot_is_archived_as_superseded(
    tmp_path: Path, content: str
) -> None:
    first = _store(tmp_path, "run-1")
    first.write_products([_product("9")])
    first.publish(_manifest("run-1"), catalog_outcome="accepted", publish_coupons=False)
    location = _location(tmp_path)
    (location / "2026-09-23" / "manifest.json").write_text(content, encoding="utf-8")

    second = _store(tmp_path, "run-2")
    second.write_products([_product("8")])
    second.publish(
        _manifest("run-2"), catalog_outcome="accepted", publish_coupons=False
    )

    archived = [path.name for path in (location / "attempts" / "2026-09-23").iterdir()]
    assert archived == ["superseded-20260923T000000000000Z"]
