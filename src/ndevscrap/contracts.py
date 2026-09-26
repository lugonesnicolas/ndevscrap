"""Shared protocol boundaries for connectors, stores and adapters."""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Protocol, TypeVar

from .models import RunManifest
from .quality import QualityPolicy

SnapshotOutcome = Literal["accepted", "quarantined", "failed", "failed_transient"]


class AuthenticationRequiredError(RuntimeError):
    """Session material is missing, invalid or rejected; a person must act."""


@dataclass(frozen=True, slots=True)
class ConnectorMetadata:
    connector_id: str
    version: str
    owner: str
    access_method: str
    schema_version: str


@dataclass(frozen=True, slots=True)
class RunContext:
    run_id: str
    store: str
    postal_code: str
    captured_at: datetime


@dataclass(frozen=True, slots=True)
class HttpRequest:
    method: str
    url: str
    params: Mapping[str, str | int | bool] = field(default_factory=dict)
    headers: Mapping[str, str] = field(default_factory=dict)
    cookies: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    url: str
    headers: Mapping[str, str]
    body: bytes

    def json(self) -> Any:
        import json

        return json.loads(self.body)


@dataclass(frozen=True, slots=True)
class RawRecord:
    key: str
    source_url: str
    payload: Any
    fetched_at: datetime


@dataclass(frozen=True, slots=True)
class SourceItem:
    key: str
    request: HttpRequest
    prefetched: RawRecord | None = None


class NormalizedRecord(Protocol):
    def to_dict(self) -> dict[str, Any]: ...


NormalizedT = TypeVar("NormalizedT", bound=NormalizedRecord)


class Connector(Protocol[NormalizedT]):
    metadata: ConnectorMetadata

    def discover(self, context: RunContext) -> Iterable[SourceItem]: ...

    def extract(self, item: SourceItem, context: RunContext) -> RawRecord: ...

    def normalize(
        self, record: RawRecord, context: RunContext
    ) -> Iterable[NormalizedT]: ...


def _empty_counts() -> Mapping[int, int]:
    return MappingProxyType({})


@dataclass(frozen=True, slots=True)
class TransportStats:
    requests: int = 0
    retries: int = 0
    status_counts: Mapping[int, int] = field(default_factory=_empty_counts)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "status_counts", MappingProxyType(dict(self.status_counts))
        )

    def since(self, before: TransportStats) -> TransportStats:
        counts = {
            status: count - before.status_counts.get(status, 0)
            for status, count in self.status_counts.items()
        }
        return TransportStats(
            requests=self.requests - before.requests,
            retries=self.retries - before.retries,
            status_counts={status: count for status, count in counts.items() if count},
        )


class Transport(Protocol):
    def request(self, request: HttpRequest) -> HttpResponse: ...

    def stats(self) -> TransportStats: ...


@dataclass(frozen=True, slots=True)
class SessionMaterial:
    headers: Mapping[str, str]
    cookies: Mapping[str, str]


class SessionProvider(Protocol):
    def load(self) -> SessionMaterial: ...


@dataclass(frozen=True, slots=True)
class ComponentSpec:
    """One executable part of a store, such as a catalog or a coupon feed."""

    name: str
    label: str
    output_file: str
    metadata: ConnectorMetadata
    connector: Connector[Any] | None
    critical: bool
    persist_raw: bool
    sensitive: bool = False
    unavailable: str | None = None
    validator: Callable[[Any], bool] | None = None
    record_key: Callable[[Any], Hashable] | None = None
    quality: QualityPolicy | None = None


class StoreDefinition(Protocol):
    """The only place that knows a concrete store and how it is composed."""

    store_id: str
    platform: str
    timezone: str

    def validate(self) -> None: ...

    def public_settings(self) -> Mapping[str, Any]: ...

    def components(self, transport: Transport) -> Sequence[ComponentSpec]: ...


@dataclass(frozen=True, slots=True)
class StoredComponent:
    output_file: str
    critical: bool


class SnapshotStore(Protocol):
    def prepare(self) -> None: ...

    def write_raw(self, component: str, record: RawRecord) -> None: ...

    def write_rejected(self, component: str, record: RawRecord) -> None: ...

    def read_raw(self, component: str, key: str) -> RawRecord | None: ...

    def write_normalized(
        self, component: str, rows: Iterable[NormalizedRecord]
    ) -> int: ...

    def published_count(self, component: str) -> int | None: ...

    def publish(
        self,
        manifest: RunManifest,
        *,
        outcome: SnapshotOutcome,
        published: AbstractSet[str],
    ) -> Path: ...

    def abort(self) -> None: ...
