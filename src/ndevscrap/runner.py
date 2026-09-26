"""Run orchestration independent from platform adapters."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import DiaConfig
from .connectors.clubdia import ClubDiaAuthenticationError, ClubDiaConnector
from .connectors.vtex import VtexConnector
from .contracts import CatalogOutcome, RunContext, Transport
from .models import ComponentResult, CouponSnapshot, ProductSnapshot, RunManifest
from .quality import evaluate_products
from .session import JsonFileSessionProvider, SessionConfigurationError
from .storage import FileSnapshotStore
from .transport import (
    RETRYABLE_STATUS_CODES,
    HttpStatusError,
    RequestsTransport,
    TransportError,
)

LOGGER = logging.getLogger(__name__)


def run_dia(
    config: DiaConfig,
    *,
    transport: Transport | None = None,
    clock: Callable[[], datetime] | None = None,
) -> tuple[RunManifest, Path]:
    config.validate()
    zone = ZoneInfo(config.timezone)
    now = clock or (lambda: datetime.now(zone))
    started = now()
    started_clock = time.monotonic()
    run_id = str(uuid.uuid4())
    snapshot_id = f"dia:{config.postal_code}:{started.date().isoformat()}"
    context = RunContext(
        run_id=run_id,
        store="dia",
        postal_code=config.postal_code,
        captured_at=started,
    )
    store = FileSnapshotStore(
        config.output_dir,
        store="dia",
        postal_code=config.postal_code,
        snapshot_date=started.date(),
        run_id=run_id,
    )
    store.prepare()
    if transport is None:
        transport = _default_transport(config)

    catalog, catalog_outcome = _catalog_component(config, context, transport, store)
    clubdia = _clubdia_component(config, context, transport, store)
    components = {"catalog": catalog, "clubdia": clubdia}

    if catalog.status != "success":
        status = "failed"
    elif clubdia.status in {"failed", "authentication_required"}:
        status = "partial_success"
    else:
        status = "success"
    manifest = RunManifest(
        run_id=run_id,
        snapshot_id=snapshot_id,
        connector_version=VtexConnector.metadata.version,
        store="dia",
        postal_code=config.postal_code,
        started_at=started,
        finished_at=now(),
        configuration_hash=config.public_hash(),
        status=status,
        components=components,
        duration_seconds=round(time.monotonic() - started_clock, 3),
    )
    destination = store.publish(
        manifest,
        catalog_outcome=catalog_outcome,
        publish_coupons=clubdia.status == "success",
    )
    return manifest, destination


def _default_transport(config: DiaConfig) -> RequestsTransport:
    user_agent = "NDevScrap/0.1"
    if config.contact:
        user_agent = f"{user_agent} ({config.contact})"
    return RequestsTransport(
        timeout_seconds=config.timeout_seconds,
        requests_per_second=config.requests_per_second,
        max_retries=config.max_retries,
        user_agent=user_agent,
    )


def _catalog_component(
    config: DiaConfig,
    context: RunContext,
    transport: Transport,
    store: FileSnapshotStore,
) -> tuple[ComponentResult, CatalogOutcome]:
    result = ComponentResult(status="running")
    retries_before = transport.retries
    outcome: CatalogOutcome
    try:
        products = _run_catalog(config, context, transport, store, result)
        quality = evaluate_products(products, store.previous_product_count())
        result.rejected += quality.rejected
        result.errors.extend(quality.errors)
        result.normalized = store.write_products(quality.products)
        result.status = "success" if quality.ok else "quality_failure"
        outcome = "accepted" if quality.ok else "quarantined"
    except Exception as exc:  # component boundary: isolate any catalog failure
        result.status = "failed"
        result.errors.append(f"{type(exc).__name__}: {exc}")
        outcome = "failed_transient" if _is_transient(exc) else "failed"
        LOGGER.error(
            "catalog component failed: %s: %s",
            type(exc).__name__,
            exc,
            extra={"run_id": context.run_id},
        )
        LOGGER.debug("catalog failure traceback", exc_info=True)
    finally:
        result.retries = transport.retries - retries_before
    return result, outcome


def _run_catalog(
    config: DiaConfig,
    context: RunContext,
    transport: Transport,
    store: FileSnapshotStore,
    result: ComponentResult,
) -> list[ProductSnapshot]:
    connector = VtexConnector(config, transport)
    products: list[ProductSnapshot] = []
    for item in connector.discover(context):
        record = item.prefetched or store.read_raw("catalog", item.key)
        if record is None:
            record = connector.extract(item, context)
        try:
            normalized = tuple(connector.normalize(record, context))
        except Exception:
            store.write_rejected("catalog", record)
            raise
        store.write_raw("catalog", record)
        products.extend(normalized)
        result.discovered += len(normalized)
    return products


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, HttpStatusError):
        return exc.status_code in RETRYABLE_STATUS_CODES
    return isinstance(exc, TransportError)


def _clubdia_component(
    config: DiaConfig,
    context: RunContext,
    transport: Transport,
    store: FileSnapshotStore,
) -> ComponentResult:
    retries_before = transport.retries
    result = ComponentResult(status="running")
    try:
        coupons, result = _run_clubdia(config, context, transport)
        if coupons is not None:
            result.normalized = store.write_coupons(coupons)
    except Exception as exc:  # noqa: BLE001 - component boundary
        # Session material may travel in exception messages or chained causes,
        # so only the exception type is recorded and no traceback is logged.
        result = ComponentResult(
            status="failed",
            errors=[f"{type(exc).__name__}: unexpected ClubDIA failure"],
        )
        LOGGER.error(
            "clubdia component failed: %s",
            type(exc).__name__,
            extra={"run_id": context.run_id},
        )
    finally:
        result.retries = transport.retries - retries_before
    return result


def _run_clubdia(
    config: DiaConfig,
    context: RunContext,
    transport: Transport,
) -> tuple[tuple[CouponSnapshot, ...] | None, ComponentResult]:
    if not config.session_file:
        return None, ComponentResult(
            status="authentication_required",
            errors=["Set NDEVSCRAP_DIA_SESSION_FILE to include ClubDIA coupons"],
        )
    connector = ClubDiaConnector(
        config.base_url,
        transport,
        JsonFileSessionProvider(config.session_file),
    )
    try:
        coupons: list[CouponSnapshot] = []
        for item in connector.discover(context):
            record = connector.extract(item, context)
            coupons.extend(connector.normalize(record, context))
        return tuple(coupons), ComponentResult(
            status="success",
            discovered=len(coupons),
        )
    except (ClubDiaAuthenticationError, SessionConfigurationError) as exc:
        return None, ComponentResult(
            status="authentication_required",
            errors=[f"{type(exc).__name__}: ClubDIA session unavailable or rejected"],
        )
    except HttpStatusError as exc:
        if exc.status_code in {401, 403}:
            return None, ComponentResult(
                status="authentication_required",
                errors=[f"ClubDIA session rejected with HTTP {exc.status_code}"],
            )
        return None, ComponentResult(
            status="failed",
            errors=[f"ClubDIA request failed with HTTP {exc.status_code}"],
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return None, ComponentResult(
            status="failed",
            errors=[f"{type(exc).__name__}: ClubDIA request failed"],
        )
