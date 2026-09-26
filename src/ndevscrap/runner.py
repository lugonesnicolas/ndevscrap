"""Run orchestration for any store definition, independent from adapters."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import __version__
from .config import HttpSettings, RunSettings, configuration_hash
from .contracts import (
    AuthenticationRequiredError,
    ComponentSpec,
    RunContext,
    SnapshotOutcome,
    StoredComponent,
    StoreDefinition,
    Transport,
)
from .models import ComponentResult, RunManifest
from .quality import QualityGate, evaluate_counts
from .storage import FileSnapshotStore, is_safe_identifier, is_safe_output_file
from .transport import (
    RETRYABLE_STATUS_CODES,
    HttpStatusError,
    RequestBuildError,
    TransportError,
    UnexpectedRedirectError,
    build_transport,
)

LOGGER = logging.getLogger(__name__)
_SESSION_REJECTED = frozenset({401, 403})


def run_store(
    definition: StoreDefinition,
    run_settings: RunSettings,
    http_settings: HttpSettings,
    *,
    transport: Transport | None = None,
    clock: Callable[[], datetime] | None = None,
) -> tuple[RunManifest, Path]:
    run_settings.validate()
    http_settings.validate()
    definition.validate()
    if not is_safe_identifier(definition.store_id):
        raise ValueError("store_id must be a lowercase identifier")
    zone = _zone(definition.timezone)
    now = clock or (lambda: datetime.now(zone))
    started = now()
    started_clock = time.monotonic()
    run_id = str(uuid.uuid4())
    postal_code = run_settings.postal_code
    context = RunContext(
        run_id=run_id,
        store=definition.store_id,
        postal_code=postal_code,
        captured_at=started,
    )
    if transport is None:
        transport = build_transport(http_settings, run_settings.contact)
    specs = tuple(definition.components(transport))
    _validate_composition(specs)
    store = FileSnapshotStore(
        run_settings.output_dir,
        store=definition.store_id,
        postal_code=postal_code,
        snapshot_date=started.date(),
        run_id=run_id,
        components={
            spec.name: StoredComponent(spec.output_file, spec.critical)
            for spec in specs
        },
    )
    # Computed before any file is written so that an invalid public
    # configuration is a configuration error, not a failure after scraping.
    config_hash = configuration_hash(
        store_id=definition.store_id,
        platform=definition.platform,
        postal_code=postal_code,
        http=http_settings,
        store_settings=definition.public_settings(),
        contact_configured=bool(run_settings.contact),
    )
    fields = {"run_id": run_id, "store": definition.store_id}
    _log(logging.INFO, "run_started", **fields)
    store.prepare()

    results: dict[str, ComponentResult] = {}
    outcome: SnapshotOutcome = "failed"
    for spec in specs:
        result, component_outcome = _run_component(spec, context, transport, store)
        results[spec.name] = result
        if spec.critical:
            outcome = component_outcome

    published = frozenset(
        spec.name
        for spec in specs
        if (
            outcome == "accepted"
            if spec.critical
            else results[spec.name].status == "success"
        )
    )
    for name, result in results.items():
        result.published = name in published
    manifest = RunManifest(
        run_id=run_id,
        snapshot_id=f"{definition.store_id}:{postal_code}:{started.date().isoformat()}",
        platform=definition.platform,
        store=definition.store_id,
        location={"postal_code": postal_code},
        package_version=__version__,
        configuration_hash=config_hash,
        status=_run_status(specs, results),
        started_at=started,
        finished_at=now(),
        duration_seconds=round(time.monotonic() - started_clock, 3),
        components=results,
    )
    try:
        destination = store.publish(manifest, outcome=outcome, published=published)
    except Exception as exc:
        _log(
            logging.ERROR,
            "run_failed",
            "publication failed",
            exc_type=type(exc).__name__,
            **fields,
        )
        raise
    _log(logging.INFO, "run_finished", status=manifest.status, **fields)
    return manifest, destination


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("store timezone is not a valid IANA zone") from None


def _validate_composition(specs: Sequence[ComponentSpec]) -> None:
    names = [spec.name for spec in specs]
    files = [spec.output_file.casefold() for spec in specs]
    if not specs or len(set(names)) != len(names) or len(set(files)) != len(files):
        raise ValueError("store components need unique names and output files")
    critical = [spec for spec in specs if spec.critical]
    if len(critical) != 1:
        raise ValueError("a store needs exactly one critical component")
    for spec in specs:
        _validate_component(spec)


def _validate_component(spec: ComponentSpec) -> None:
    if not is_safe_identifier(spec.name) or not is_safe_output_file(spec.output_file):
        raise ValueError(f"component {spec.name!r} has an unsafe name or output file")
    if spec.sensitive and spec.persist_raw:
        raise ValueError(f"sensitive component {spec.name!r} cannot persist raw")
    if spec.connector is None and spec.unavailable is None:
        raise ValueError(f"component {spec.name!r} needs a connector or a reason")
    if spec.connector is not None and spec.connector.metadata != spec.metadata:
        raise ValueError(f"component {spec.name!r} metadata differs from its connector")
    if spec.critical:
        if spec.connector is None or spec.unavailable is not None:
            raise ValueError("the critical component must be available")
        if spec.sensitive:
            raise ValueError("the critical component cannot be sensitive")
        if not spec.persist_raw:
            raise ValueError("the critical component must persist raw")
    elif spec.quality is not None:
        raise ValueError("only the critical component can declare a quality policy")


def _run_component(
    spec: ComponentSpec,
    context: RunContext,
    transport: Transport,
    store: FileSnapshotStore,
) -> tuple[ComponentResult, SnapshotOutcome]:
    fields = {"run_id": context.run_id, "store": context.store, "component": spec.name}
    _log(logging.INFO, "component_started", **fields)
    result = ComponentResult(
        status="running",
        connector_id=spec.metadata.connector_id,
        connector_version=spec.metadata.version,
    )
    outcome: SnapshotOutcome = "failed"
    before = transport.stats()
    started = time.monotonic()
    try:
        if spec.connector is None or spec.unavailable is not None:
            result.status = "authentication_required"
            result.errors.append(spec.unavailable or "component is unavailable")
        else:
            outcome = _collect(spec, context, store, result)
    except Exception as exc:  # noqa: BLE001 - component boundary isolates failures
        result.status, message, outcome = _classify(spec, exc)
        result.errors.append(message)
        # A sensitive component may carry session material in the exception
        # text or chain, so only the fixed message is logged, without exc_info.
        _log(
            logging.ERROR,
            "component_failed",
            f"component failed: {message}",
            status=result.status,
            **fields,
        )
    finally:
        delta = transport.stats().since(before)
        result.retries = delta.retries
        result.requests = delta.requests
        result.http_status_counts = dict(delta.status_counts)
        result.duration_seconds = round(time.monotonic() - started, 3)
    _log(
        logging.INFO,
        "component_finished",
        status=result.status,
        discovered=result.discovered,
        normalized=result.normalized,
        rejected=result.rejected,
        duplicates=result.duplicates,
        retries=result.retries,
        requests=result.requests,
        duration_seconds=result.duration_seconds,
        **fields,
    )
    return result, outcome


def _collect(
    spec: ComponentSpec,
    context: RunContext,
    store: FileSnapshotStore,
    result: ComponentResult,
) -> SnapshotOutcome:
    gate = QualityGate(validator=spec.validator, record_key=spec.record_key)
    try:
        result.normalized = store.write_normalized(
            spec.name, gate.filter(_stream(spec, context, store))
        )
    finally:
        result.discovered = gate.discovered
        result.rejected = gate.rejected
        result.duplicates = gate.duplicates
    errors: tuple[str, ...] = ()
    if spec.quality is not None:
        errors = evaluate_counts(
            spec.quality,
            valid=result.normalized,
            discovered=gate.discovered,
            rejected=gate.rejected,
            baseline=store.published_count(spec.name),
        )
    result.errors.extend(errors)
    result.status = "quality_failure" if errors else "success"
    return "quarantined" if errors else "accepted"


def _stream(
    spec: ComponentSpec, context: RunContext, store: FileSnapshotStore
) -> Iterator[Any]:
    """Yield each page's rows before the next page is acquired."""
    connector = spec.connector
    assert connector is not None
    for item in connector.discover(context):
        record = item.prefetched
        if record is None and spec.persist_raw:
            record = store.read_raw(spec.name, item.key)
        if record is None:
            record = connector.extract(item, context)
        try:
            rows = tuple(connector.normalize(record, context))
        except Exception:
            if spec.persist_raw:
                store.write_rejected(spec.name, record)
            raise
        if spec.persist_raw:
            store.write_raw(spec.name, record)
        yield from rows


def _classify(spec: ComponentSpec, exc: Exception) -> tuple[str, str, SnapshotOutcome]:
    kind = type(exc).__name__
    if not spec.sensitive:
        return "failed", f"{kind}: {exc}", _outcome_for(exc)
    label = spec.label
    if isinstance(exc, AuthenticationRequiredError):
        return (
            "authentication_required",
            f"{kind}: {label} session unavailable or rejected",
            "failed",
        )
    if isinstance(exc, HttpStatusError):
        code = exc.status_code
        if code in _SESSION_REJECTED or 300 <= code < 400:
            return (
                "authentication_required",
                f"{label} session rejected with HTTP {code}",
                "failed",
            )
        return "failed", f"{label} request failed with HTTP {code}", "failed"
    if isinstance(exc, (OSError, RuntimeError, TypeError, ValueError)):
        return "failed", f"{kind}: {label} request failed", "failed"
    return "failed", f"{kind}: unexpected {label} failure", "failed"


def _outcome_for(exc: Exception) -> SnapshotOutcome:
    if isinstance(exc, HttpStatusError):
        return (
            "failed_transient"
            if exc.status_code in RETRYABLE_STATUS_CODES
            else "failed"
        )
    if isinstance(exc, (RequestBuildError, UnexpectedRedirectError)):
        return "failed"
    return "failed_transient" if isinstance(exc, TransportError) else "failed"


def _run_status(
    specs: Sequence[ComponentSpec], results: dict[str, ComponentResult]
) -> str:
    critical = next(spec for spec in specs if spec.critical)
    if results[critical.name].status != "success":
        return "failed"
    if any(result.status != "success" for result in results.values()):
        return "partial_success"
    return "success"


def _log(level: int, event: str, message: str | None = None, **fields: object) -> None:
    LOGGER.log(level, message or event, extra={"event": event, **fields})
