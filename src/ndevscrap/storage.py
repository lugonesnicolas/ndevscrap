"""Atomic filesystem snapshot storage."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import zlib
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .contracts import CatalogOutcome, RawRecord
from .models import CouponSnapshot, ProductSnapshot, RunManifest

_SAFE = re.compile(r"[^a-zA-Z0-9_.-]+")
_INDEX_KIND = "current-index"
_INDEX_VERSION = "1"
_COMPONENT_FILES = {"catalog": "products.jsonl", "clubdia": "coupons.jsonl"}
_RESUMABLE_ENTRIES = frozenset({"raw", "checkpoint.json"})


class FileSnapshotStore:
    """Stage a daily snapshot and publish current only from accepted data.

    Layout under ``<output>/<store>/<postal_code>/``: ``<date>/`` holds the last
    accepted attempt of the day, ``attempts/<date>/<run_id>/`` keeps every other
    attempt and superseded snapshots, ``current/`` holds the published files and
    an index with their provenance, and ``.staging-<date>/`` survives only a
    transient failure so the next run can resume from confirmed raw pages.
    ``checkpoint.json`` is informational; resumption relies on ``read_raw``.
    """

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
        self._store = _safe_name(store)
        self._postal_code = _safe_name(postal_code)
        self._location_root = (self._root / self._store / self._postal_code).resolve()
        day = snapshot_date.isoformat()
        self._snapshot = self._location_root / day
        self._current = self._location_root / "current"
        self._staging = self._location_root / f".staging-{day}"
        self._attempts = self._location_root / "attempts" / day
        _assert_within(self._location_root, self._root)
        _assert_within(self._staging, self._root)

    def prepare(self) -> None:
        self._location_root.mkdir(parents=True, exist_ok=True)
        for leftover in self._location_root.glob(".current-*"):
            _safe_rmtree(leftover, self._root)
        if self._staging.exists():
            self._clear_staging_for_resume()
        (self._staging / "raw").mkdir(parents=True, exist_ok=True)
        (self._staging / "normalized").mkdir(exist_ok=True)

    def write_raw(self, component: str, record: RawRecord) -> None:
        _write_envelope(self._staging / "raw" / _safe_name(component), record)
        self._record_checkpoint(component, record.key)

    def write_rejected(self, component: str, record: RawRecord) -> None:
        _write_envelope(self._staging / "rejected" / _safe_name(component), record)

    def read_raw(self, component: str, key: str) -> RawRecord | None:
        path = (
            self._staging / "raw" / _safe_name(component) / f"{_safe_name(key)}.json.gz"
        )
        try:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                envelope = json.load(handle)
            if envelope["key"] != key:
                # Different keys can sanitize to the same file name.
                return None
            return RawRecord(
                key=str(envelope["key"]),
                source_url=str(envelope["source_url"]),
                payload=envelope["payload"],
                fetched_at=datetime.fromisoformat(str(envelope["fetched_at"])),
            )
        except (
            EOFError,
            OSError,
            KeyError,
            TypeError,
            ValueError,
            zlib.error,
        ):
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
        index = _read_index(self._current / "manifest.json")
        if index is not None:
            entry = index["components"].get("catalog")
            if isinstance(entry, dict) and isinstance(entry.get("records"), int):
                return entry["records"]
        return _count_rows(self._current / "products.jsonl")

    def publish(
        self,
        manifest: RunManifest,
        *,
        catalog_outcome: CatalogOutcome,
        publish_coupons: bool,
    ) -> Path:
        index = self._load_index()
        published = {
            "catalog": catalog_outcome == "accepted",
            "clubdia": publish_coupons,
        }
        if catalog_outcome == "accepted":
            return self._publish_accepted(manifest, index, published)
        if catalog_outcome == "failed_transient":
            destination = self._record_transient_attempt(manifest, publish_coupons)
        else:
            destination = self._archive_staging(manifest)
        current_staging = self._build_current(
            manifest, index, destination, destination, published
        )
        self._swap_current(current_staging)
        return destination

    def abort(self) -> None:
        if self._staging.exists():
            _safe_rmtree(self._staging, self._root)

    def _clear_staging_for_resume(self) -> None:
        for entry in self._staging.iterdir():
            if entry.name in _RESUMABLE_ENTRIES:
                continue
            if entry.is_dir():
                _safe_rmtree(entry, self._root)
            else:
                entry.unlink()
        for temporary in (self._staging / "raw").rglob("*.tmp"):
            temporary.unlink()

    def _publish_accepted(
        self,
        manifest: RunManifest,
        index: dict[str, Any],
        published: dict[str, bool],
    ) -> Path:
        _write_json(self._staging / "manifest.json", manifest.to_dict())
        archived: Path | None = None
        if self._snapshot.exists():
            archived = self._new_attempt_path(
                _manifest_run_id(self._snapshot / "manifest.json"),
                manifest.finished_at,
            )
            _rewrite_sources(
                index, self._relative(self._snapshot), self._relative(archived)
            )
        # current is fully staged before the snapshot moves so that a failure at
        # any step can restore both the dated snapshot and current.
        current_staging = self._build_current(
            manifest, index, self._staging, self._snapshot, published
        )
        try:
            self._promote_staging(archived)
        except Exception:
            _safe_rmtree(current_staging, self._root)
            raise
        try:
            self._replace_directory(current_staging, self._current)
        except Exception:
            self._demote_snapshot(archived)
            if current_staging.exists():
                _safe_rmtree(current_staging, self._root)
            raise
        return self._snapshot

    def _promote_staging(self, archived: Path | None) -> None:
        if archived is not None:
            archived.parent.mkdir(parents=True, exist_ok=True)
            os.replace(self._snapshot, archived)
        try:
            os.replace(self._staging, self._snapshot)
        except Exception:
            if archived is not None and not self._snapshot.exists():
                os.replace(archived, self._snapshot)
            raise

    def _demote_snapshot(self, archived: Path | None) -> None:
        os.replace(self._snapshot, self._staging)
        if archived is not None:
            os.replace(archived, self._snapshot)

    def _swap_current(self, current_staging: Path) -> None:
        try:
            self._replace_directory(current_staging, self._current)
        except Exception:
            if current_staging.exists():
                _safe_rmtree(current_staging, self._root)
            raise

    def _archive_staging(self, manifest: RunManifest) -> Path:
        _write_json(self._staging / "manifest.json", manifest.to_dict())
        destination = self._new_attempt_path(manifest.run_id, manifest.finished_at)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(self._staging, destination)
        return destination

    def _record_transient_attempt(
        self, manifest: RunManifest, publish_coupons: bool
    ) -> Path:
        destination = self._new_attempt_path(manifest.run_id, manifest.finished_at)
        destination.mkdir(parents=True)
        coupons = self._staging / "normalized" / "coupons.jsonl"
        if publish_coupons and coupons.exists():
            (destination / "normalized").mkdir()
            shutil.copy2(coupons, destination / "normalized" / "coupons.jsonl")
        _write_json(destination / "manifest.json", manifest.to_dict())
        return destination

    def _build_current(
        self,
        manifest: RunManifest,
        index: dict[str, Any],
        files_root: Path,
        recorded_root: Path,
        published: dict[str, bool],
    ) -> Path:
        """Stage current from ``files_root``; record paths under ``recorded_root``."""
        current_staging = (
            self._location_root / f".current-{_safe_name(manifest.run_id)}"
        )
        if current_staging.exists():
            _safe_rmtree(current_staging, self._root)
        current_staging.mkdir()
        components: dict[str, Any] = index["components"]
        for component, filename in _COMPONENT_FILES.items():
            target = current_staging / filename
            source = files_root / "normalized" / filename
            if published[component] and source.exists():
                shutil.copy2(source, target)
                components[component] = self._run_entry(
                    manifest, component, target, recorded_root / "normalized" / filename
                )
            elif (self._current / filename).exists():
                shutil.copy2(self._current / filename, target)
            else:
                components.pop(component, None)
        index["last_attempt"] = {
            "run_id": manifest.run_id,
            "status": manifest.status,
            "finished_at": manifest.finished_at.isoformat(),
            "manifest": self._relative(recorded_root / "manifest.json"),
        }
        _write_json(current_staging / "manifest.json", index)
        return current_staging

    def _load_index(self) -> dict[str, Any]:
        index = _read_index(self._current / "manifest.json")
        if index is None:
            index = {
                "kind": _INDEX_KIND,
                "index_version": _INDEX_VERSION,
                "store": self._store,
                "postal_code": self._postal_code,
                "components": {},
                "last_attempt": None,
            }
        components: dict[str, Any] = index["components"]
        for component, filename in _COMPONENT_FILES.items():
            path = self._current / filename
            if component not in components and path.exists():
                components[component] = _legacy_entry(path)
        return index

    def _run_entry(
        self, manifest: RunManifest, component: str, target: Path, source: Path
    ) -> dict[str, Any]:
        records = _count_rows(target) or 0
        result = manifest.components.get(component)
        return {
            "run_id": manifest.run_id,
            "snapshot_id": manifest.snapshot_id,
            "published_at": manifest.finished_at.isoformat(),
            "status": result.status if result is not None else None,
            "records": records,
            "normalized": records,
            "sha256": _sha256(target),
            "file": target.name,
            "source": self._relative(source),
            "provenance": "run",
        }

    def _new_attempt_path(self, run_id: str | None, moment: datetime) -> Path:
        try:
            name = _safe_name(run_id) if run_id else ""
        except ValueError:
            name = ""
        if not name:
            name = f"superseded-{moment.astimezone(UTC):%Y%m%dT%H%M%S%fZ}"
        candidate = self._attempts / name
        suffix = 1
        while candidate.exists():
            candidate = self._attempts / f"{name}-{suffix}"
            suffix += 1
        _assert_within(candidate, self._root)
        return candidate

    def _relative(self, path: Path) -> str:
        return path.relative_to(self._location_root).as_posix()

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


def _read_index(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (
        isinstance(data, dict)
        and data.get("kind") == _INDEX_KIND
        and isinstance(data.get("components"), dict)
    ):
        return data
    return None


def _legacy_entry(path: Path) -> dict[str, Any]:
    records = _count_rows(path) or 0
    return {
        "run_id": None,
        "snapshot_id": None,
        "published_at": None,
        "status": None,
        "records": records,
        "normalized": records,
        "sha256": _sha256(path),
        "file": path.name,
        "source": None,
        "provenance": "legacy",
    }


def _rewrite_sources(index: dict[str, Any], old_prefix: str, new_prefix: str) -> None:
    def rewrite(value: Any) -> Any:
        if isinstance(value, str) and value.startswith(f"{old_prefix}/"):
            return f"{new_prefix}{value.removeprefix(old_prefix)}"
        return value

    for entry in index["components"].values():
        if isinstance(entry, dict):
            entry["source"] = rewrite(entry.get("source"))
    last_attempt = index.get("last_attempt")
    if isinstance(last_attempt, dict):
        last_attempt["manifest"] = rewrite(last_attempt.get("manifest"))


def _manifest_run_id(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = data.get("run_id") if isinstance(data, dict) else None
    return value if isinstance(value, str) and value else None


def _write_envelope(directory: Path, record: RawRecord) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_safe_name(record.key)}.json.gz"
    temporary = path.with_name(f"{path.name}.tmp")
    envelope = {
        "key": record.key,
        "source_url": record.source_url,
        "fetched_at": record.fetched_at.isoformat(),
        "payload": record.payload,
    }
    with gzip.open(temporary, "wt", encoding="utf-8") as handle:
        json.dump(envelope, handle, ensure_ascii=False, separators=(",", ":"))
    os.replace(temporary, path)


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


def _count_rows(path: Path) -> int | None:
    try:
        with path.open("rb") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
