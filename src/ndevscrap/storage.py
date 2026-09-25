"""Atomic filesystem snapshot storage."""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .contracts import RawRecord
from .models import CouponSnapshot, ProductSnapshot, RunManifest

_SAFE = re.compile(r"[^a-zA-Z0-9_.-]+")


class FileSnapshotStore:
    def __init__(
        self,
        output_dir: Path,
        *,
        store: str,
        postal_code: str,
        snapshot_date: date,
        run_id: str,
    ) -> None:
        self._root = output_dir.resolve()
        location = _safe_name(postal_code)
        store_name = _safe_name(store)
        self._location_root = (self._root / store_name / location).resolve()
        self._snapshot = self._location_root / snapshot_date.isoformat()
        self._current = self._location_root / "current"
        self._staging = self._location_root / f".staging-{snapshot_date.isoformat()}"
        _assert_within(self._location_root, self._root)
        _assert_within(self._staging, self._root)

    def prepare(self) -> None:
        self._location_root.mkdir(parents=True, exist_ok=True)
        (self._staging / "raw").mkdir(parents=True, exist_ok=True)
        (self._staging / "normalized").mkdir(exist_ok=True)

    def write_raw(self, component: str, record: RawRecord) -> None:
        destination = self._staging / "raw" / _safe_name(component)
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / f"{_safe_name(record.key)}.json.gz"
        envelope = {
            "key": record.key,
            "source_url": record.source_url,
            "fetched_at": record.fetched_at.isoformat(),
            "payload": record.payload,
        }
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            json.dump(envelope, handle, ensure_ascii=False, separators=(",", ":"))
        self._record_checkpoint(component, record.key)

    def read_raw(self, component: str, key: str) -> RawRecord | None:
        path = (
            self._staging / "raw" / _safe_name(component) / f"{_safe_name(key)}.json.gz"
        )
        try:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                envelope = json.load(handle)
            return RawRecord(
                key=str(envelope["key"]),
                source_url=str(envelope["source_url"]),
                payload=envelope["payload"],
                fetched_at=datetime.fromisoformat(str(envelope["fetched_at"])),
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def write_products(self, products: Iterable[ProductSnapshot]) -> int:
        return _write_jsonl(
            self._staging / "normalized" / "products.jsonl",
            (product.to_dict() for product in products),
        )

    def write_coupons(self, coupons: Iterable[CouponSnapshot]) -> int:
        return _write_jsonl(
            self._staging / "normalized" / "coupons.jsonl",
            (coupon.to_dict() for coupon in coupons),
        )

    def previous_product_count(self) -> int | None:
        manifest_path = self._current / "manifest.json"
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            value = data["components"]["catalog"]["normalized"]
            return int(value)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None

    def publish(
        self,
        manifest: RunManifest,
        *,
        publish_catalog: bool,
        publish_coupons: bool,
    ) -> Path:
        _write_json(self._staging / "manifest.json", manifest.to_dict())
        self._replace_directory(self._staging, self._snapshot)

        current_staging = self._location_root / f".current-{manifest.run_id}"
        if current_staging.exists():
            _safe_rmtree(current_staging, self._root)
        current_staging.mkdir()
        if publish_catalog:
            _copy_if_exists(
                self._snapshot / "normalized" / "products.jsonl",
                current_staging / "products.jsonl",
            )
        else:
            _copy_if_exists(
                self._current / "products.jsonl", current_staging / "products.jsonl"
            )
        if publish_coupons:
            _copy_if_exists(
                self._snapshot / "normalized" / "coupons.jsonl",
                current_staging / "coupons.jsonl",
            )
        else:
            _copy_if_exists(
                self._current / "coupons.jsonl", current_staging / "coupons.jsonl"
            )
        _write_json(current_staging / "manifest.json", manifest.to_dict())
        self._replace_directory(current_staging, self._current)
        return self._snapshot

    def abort(self) -> None:
        if self._staging.exists():
            _safe_rmtree(self._staging, self._root)

    def _record_checkpoint(self, component: str, key: str) -> None:
        path = self._staging / "checkpoint.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {"completed": {}}
        completed = data.setdefault("completed", {})
        keys = completed.setdefault(component, [])
        if key not in keys:
            keys.append(key)
            keys.sort()
        _write_json(path, data)

    def _replace_directory(self, source: Path, destination: Path) -> None:
        _assert_within(source, self._root)
        _assert_within(destination, self._root)
        backup = destination.with_name(f".{destination.name}.backup")
        if backup.exists():
            _safe_rmtree(backup, self._root)
        if destination.exists():
            os.replace(destination, backup)
        try:
            os.replace(source, destination)
        except Exception:
            if backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
        if backup.exists():
            _safe_rmtree(backup, self._root)


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
            count += 1
        handle.flush()
        os.fsync(handle.fileno())
    return count


def _write_json(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _copy_if_exists(source: Path, destination: Path) -> None:
    if source.exists():
        shutil.copy2(source, destination)


def _safe_name(value: str) -> str:
    result = _SAFE.sub("-", value.strip()).strip("-.")
    if not result:
        raise ValueError("path component is empty after sanitization")
    return result


def _assert_within(path: Path, root: Path) -> None:
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"path {resolved} is outside output root {root}")


def _safe_rmtree(path: Path, root: Path) -> None:
    _assert_within(path, root)
    if path.resolve() == root:
        raise ValueError("refusing to remove output root")
    shutil.rmtree(path)
