"""Run orchestration independent from platform adapters."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import DiaConfig
from .connectors.clubdia import ClubDiaAuthenticationError, ClubDiaConnector
from .connectors.vtex import VtexConnector
from .contracts import RunContext
from .models import ComponentResult, CouponSnapshot, ProductSnapshot, RunManifest
from .quality import evaluate_products
from .session import JsonFileSessionProvider, SessionConfigurationError
from .storage import FileSnapshotStore
from .transport import HttpStatusError, RequestsTransport

LOGGER = logging.getLogger(__name__)


def run_dia(config: DiaConfig) -> tuple[RunManifest, Path]:
    config.validate()
    zone = ZoneInfo(config.timezone)
    started = datetime.now(zone)
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
    user_agent = "NDevScrap/0.1"
    if config.contact:
        user_agent = f"{user_agent} ({config.contact})"
    transport = RequestsTransport(
        timeout_seconds=config.timeout_seconds,
        requests_per_second=config.requests_per_second,
        max_retries=config.max_retries,
        user_agent=user_agent,
    )
    components: dict[str, ComponentResult] = {}
    publish_catalog = False
    publish_coupons = False

    try:
        products, catalog = _run_catalog(config, context, transport, store)
        quality = evaluate_products(products, store.previous_product_count())
        catalog.rejected += quality.rejected
        catalog.errors.extend(quality.errors)
        catalog.normalized = store.write_products(quality.products)
        catalog.status = "success" if quality.ok else "quality_failure"
        publish_catalog = quality.ok
        components["catalog"] = catalog

        coupons, club = _run_clubdia(config, context, transport)
        if coupons is not None:
            club.normalized = store.write_coupons(coupons)
            publish_coupons = club.status == "success"
        components["clubdia"] = club
    except Exception as exc:
        LOGGER.exception("DIA run failed", extra={"run_id": run_id})
        catalog = components.setdefault("catalog", ComponentResult(status="failed"))
        catalog.status = "failed"
        catalog.errors.append(str(exc))
        components.setdefault("clubdia", ComponentResult(status="skipped"))

    finished = datetime.now(zone)
    catalog_status = components["catalog"].status
    club_status = components["clubdia"].status
    if catalog_status != "success":
        status = "failed"
    elif club_status in {"failed", "authentication_required"}:
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
        finished_at=finished,
        configuration_hash=config.public_hash(),
        status=status,
        components=components,
        duration_seconds=round(time.monotonic() - started_clock, 3),
    )
    destination = store.publish(
        manifest,
        publish_catalog=publish_catalog,
        publish_coupons=publish_coupons,
    )
    return manifest, destination


def _run_catalog(
    config: DiaConfig,
    context: RunContext,
    transport: RequestsTransport,
    store: FileSnapshotStore,
) -> tuple[list[ProductSnapshot], ComponentResult]:
    connector = VtexConnector(config, transport)
    result = ComponentResult(status="running")
    products: list[ProductSnapshot] = []
    for item in connector.discover(context):
        record = store.read_raw("catalog", item.key)
        if record is None:
            record = connector.extract(item, context)
            store.write_raw("catalog", record)
        normalized = tuple(connector.normalize(record, context))
        products.extend(normalized)
        result.discovered += len(normalized)
    result.retries = transport.retries
    return products, result


def _run_clubdia(
    config: DiaConfig,
    context: RunContext,
    transport: RequestsTransport,
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
            retries=transport.retries,
        )
    except (ClubDiaAuthenticationError, SessionConfigurationError) as exc:
        return None, ComponentResult(
            status="authentication_required", errors=[str(exc)]
        )
    except HttpStatusError as exc:
        if exc.status_code in {401, 403}:
            return None, ComponentResult(
                status="authentication_required",
                errors=[f"ClubDIA session rejected with HTTP {exc.status_code}"],
            )
        return None, ComponentResult(status="failed", errors=[str(exc)])
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return None, ComponentResult(status="failed", errors=[str(exc)])
