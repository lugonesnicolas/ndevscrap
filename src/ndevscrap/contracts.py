"""Shared protocol boundaries for connectors and adapters."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, TypeVar

from .models import CouponSnapshot, ProductSnapshot, RunManifest


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


NormalizedT = TypeVar("NormalizedT", ProductSnapshot, CouponSnapshot)


class Connector(Protocol[NormalizedT]):
    metadata: ConnectorMetadata

    def discover(self, context: RunContext) -> Iterable[SourceItem]: ...

    def extract(self, item: SourceItem, context: RunContext) -> RawRecord: ...

    def normalize(
        self, record: RawRecord, context: RunContext
    ) -> Iterable[NormalizedT]: ...


class Transport(Protocol):
    retries: int

    def request(self, request: HttpRequest) -> HttpResponse: ...


@dataclass(frozen=True, slots=True)
class SessionMaterial:
    headers: Mapping[str, str]
    cookies: Mapping[str, str]


class SessionProvider(Protocol):
    def load(self) -> SessionMaterial: ...


class SnapshotStore(Protocol):
    def prepare(self) -> None: ...

    def write_raw(self, component: str, record: RawRecord) -> None: ...

    def read_raw(self, component: str, key: str) -> RawRecord | None: ...

    def write_products(self, products: Iterable[ProductSnapshot]) -> int: ...

    def write_coupons(self, coupons: Iterable[CouponSnapshot]) -> int: ...

    def previous_product_count(self) -> int | None: ...

    def publish(
        self,
        manifest: RunManifest,
        *,
        publish_catalog: bool,
        publish_coupons: bool,
    ) -> Path: ...

    def abort(self) -> None: ...
