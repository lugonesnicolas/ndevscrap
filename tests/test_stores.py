from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

import ndevscrap
from ndevscrap.config import HttpSettings, RunSettings
from ndevscrap.connectors.clubdia import ClubDiaAuthenticationError, ClubDiaConnector
from ndevscrap.connectors.vtex import VtexConnector, VtexSettings
from ndevscrap.contracts import (
    AuthenticationRequiredError,
    ComponentSpec,
    ConnectorMetadata,
    HttpRequest,
    RawRecord,
    RunContext,
    SourceItem,
    Transport,
    TransportStats,
)
from ndevscrap.quality import QualityPolicy
from ndevscrap.runner import run_store
from ndevscrap.session import SessionConfigurationError
from ndevscrap.stores import REGISTRY
from ndevscrap.stores.dia import DiaSettings, DiaStore

PACKAGE = Path(ndevscrap.__file__).parent
REPOSITORY = Path(__file__).resolve().parents[1]
CORE = (
    "config",
    "contracts",
    "models",
    "observability",
    "quality",
    "runner",
    "session",
    "storage",
    "transport",
)


def _imports(path: Path, package: str) -> set[str]:
    """Return absolute module names imported by ``path``, resolving relatives."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - node.level + 1])
                module = f"{base}.{node.module}" if node.module else base
            else:
                module = node.module or ""
            modules.add(module)
            modules.update(f"{module}.{alias.name}" for alias in node.names)
    return modules


def _forbidden(modules: set[str], prefixes: tuple[str, ...]) -> set[str]:
    return {
        module
        for module in modules
        if any(
            module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes
        )
    }


def test_import_resolution_handles_relative_imports(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "from . import stores\nfrom .connectors import vtex\nfrom ..x import y\n",
        encoding="utf-8",
    )

    modules = _imports(sample, "ndevscrap.connectors")

    assert "ndevscrap.connectors.stores" in modules
    assert "ndevscrap.connectors.connectors.vtex" in modules
    assert "ndevscrap.x.y" in modules
    assert _forbidden(_imports(sample, "ndevscrap"), ("ndevscrap.stores",)) == {
        "ndevscrap.stores"
    }


@pytest.mark.parametrize("module", CORE)
def test_core_modules_do_not_import_stores_or_connectors(module: str) -> None:
    modules = _imports(PACKAGE / f"{module}.py", "ndevscrap")

    assert _forbidden(modules, ("ndevscrap.stores", "ndevscrap.connectors")) == set()


def test_platform_connector_does_not_import_the_store_layer() -> None:
    modules = _imports(PACKAGE / "connectors" / "vtex.py", "ndevscrap.connectors")

    assert (
        _forbidden(modules, ("ndevscrap.stores", "ndevscrap.connectors.clubdia"))
        == set()
    )


def test_importing_the_runner_does_not_load_stores() -> None:
    code = (
        "import sys, ndevscrap.runner;"
        "print(sorted(m for m in sys.modules"
        " if m.startswith(('ndevscrap.stores', 'ndevscrap.connectors'))))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == "[]"


def test_registry_exposes_dia() -> None:
    definition = REGISTRY["dia"]({})

    assert sorted(REGISTRY) == ["dia"]
    assert (definition.store_id, definition.platform) == ("dia", "vtex")
    assert definition.timezone == "America/Argentina/Buenos_Aires"


def test_session_errors_share_the_authentication_base() -> None:
    assert issubclass(SessionConfigurationError, AuthenticationRequiredError)
    assert issubclass(ClubDiaAuthenticationError, AuthenticationRequiredError)


class UnusedTransport:
    def request(self, request: HttpRequest):  # pragma: no cover - never called
        raise AssertionError("no requests expected")

    def stats(self) -> TransportStats:
        return TransportStats()


def test_dia_definition_composes_catalog_and_clubdia(tmp_path: Path) -> None:
    session = tmp_path / "session.json"
    store = DiaStore(
        DiaSettings(
            vtex=VtexSettings(base_url="https://shop.example"), session_file=session
        )
    )

    catalog, clubdia = store.components(UnusedTransport())

    assert (catalog.name, catalog.output_file) == ("catalog", "products.jsonl")
    assert isinstance(catalog.connector, VtexConnector)
    assert (catalog.critical, catalog.persist_raw, catalog.sensitive) == (
        True,
        True,
        False,
    )
    assert catalog.quality == QualityPolicy()
    assert catalog.record_key is not None and catalog.validator is not None
    assert (clubdia.name, clubdia.label, clubdia.output_file) == (
        "clubdia",
        "ClubDIA",
        "coupons.jsonl",
    )
    assert isinstance(clubdia.connector, ClubDiaConnector)
    assert (clubdia.critical, clubdia.persist_raw, clubdia.sensitive) == (
        False,
        False,
        True,
    )
    assert clubdia.quality is None
    assert clubdia.unavailable is None
    assert store.public_settings()["session_configured"] is True


def test_dia_without_session_marks_clubdia_unavailable() -> None:
    store = DiaStore(DiaSettings(vtex=VtexSettings(base_url="https://shop.example")))

    _, clubdia = store.components(UnusedTransport())

    assert clubdia.unavailable == (
        "Set NDEVSCRAP_DIA_SESSION_FILE to include ClubDIA coupons"
    )
    assert store.public_settings()["session_configured"] is False


def test_dia_settings_read_the_environment(tmp_path: Path) -> None:
    settings = DiaSettings.from_environment(
        {
            "NDEVSCRAP_DIA_BASE_URL": "https://shop.example/",
            "NDEVSCRAP_DIA_SESSION_FILE": str(tmp_path / "session.json"),
        }
    )

    assert settings.vtex.base_url == "https://shop.example"
    assert settings.session_file == tmp_path / "session.json"
    assert DiaSettings.from_environment({}).vtex.base_url == (
        "https://diaonline.supermercadosdia.com.ar"
    )
    assert (
        DiaSettings.from_environment({"NDEVSCRAP_DIA_SESSION_FILE": ""}).session_file
        is None
    )


def test_implicit_secrets_file_is_never_loaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secrets = tmp_path / ".secrets"
    secrets.mkdir()
    (secrets / "dia-session.json").write_text(
        json.dumps({"headers": {"order-form-id": "x"}, "cookies": {"a": "b"}}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    settings = DiaSettings.from_environment({})

    assert settings.session_file is None
    _, clubdia = DiaStore(settings).components(UnusedTransport())
    assert "NDEVSCRAP_DIA_SESSION_FILE" in (clubdia.unavailable or "")


def test_session_module_is_store_neutral() -> None:
    source = (PACKAGE / "session.py").read_text(encoding="utf-8").casefold()

    assert "club-dia" not in source
    assert "clubdia" not in source


def test_secrets_directory_is_ignored_by_git_and_docker() -> None:
    gitignore = (REPOSITORY / ".gitignore").read_text(encoding="utf-8").splitlines()
    dockerignore = (
        (REPOSITORY / ".dockerignore").read_text(encoding="utf-8").splitlines()
    )

    assert ".secrets/" in gitignore
    assert ".secrets" in dockerignore


@dataclass(frozen=True)
class Item:
    value: str

    def to_dict(self) -> dict[str, str]:
        return {"value": self.value}


class ItemsConnector:
    metadata = ConnectorMetadata(
        connector_id="items",
        version="0.0.1",
        owner="tests",
        access_method="fixture",
        schema_version="1",
    )

    def discover(self, context: RunContext) -> Iterable[SourceItem]:
        for key in ("page-1", "page-2"):
            yield SourceItem(
                key=key,
                request=HttpRequest("GET", f"https://items.example/{key}"),
                prefetched=RawRecord(
                    key=key,
                    source_url=f"https://items.example/{key}",
                    payload=[f"{key}-a", f"{key}-b"],
                    fetched_at=context.captured_at,
                ),
            )

    def extract(self, item: SourceItem, context: RunContext) -> RawRecord:
        raise AssertionError("items are prefetched")

    def normalize(self, record: RawRecord, context: RunContext) -> Iterable[Item]:
        return tuple(Item(value) for value in record.payload)


def _items_spec(**overrides: Any) -> ComponentSpec:
    spec = ComponentSpec(
        name="items",
        label="Items",
        output_file="items.jsonl",
        metadata=ItemsConnector.metadata,
        connector=ItemsConnector(),
        critical=True,
        persist_raw=True,
        record_key=lambda item: item.value,
        quality=QualityPolicy(),
    )
    return replace(spec, **overrides)


@dataclass
class FakeStore:
    specs: Sequence[ComponentSpec] = field(default_factory=lambda: [_items_spec()])
    store_id: str = "items-store"
    platform: str = "fixture"
    timezone: str = "UTC"
    settings: Mapping[str, Any] = field(default_factory=lambda: {"fixture": True})

    def validate(self) -> None:
        return None

    def public_settings(self) -> Mapping[str, Any]:
        return self.settings

    def components(self, transport: Transport) -> Sequence[ComponentSpec]:
        return list(self.specs)


def _clock() -> datetime:
    return datetime(2026, 9, 26, 10, tzinfo=ZoneInfo("UTC"))


def _run(tmp_path: Path, store: FakeStore):
    return run_store(
        store,
        RunSettings(postal_code="0000", output_dir=tmp_path / "out"),
        HttpSettings(),
        transport=UnusedTransport(),
        clock=_clock,
    )


def test_a_single_component_store_runs_on_the_generic_runner(tmp_path: Path) -> None:
    manifest, destination = _run(tmp_path, FakeStore())

    assert manifest.status == "success"
    assert (manifest.platform, manifest.store) == ("fixture", "items-store")
    location = tmp_path / "out" / "items-store" / "0000"
    assert destination == location.resolve() / "2026-09-26"
    current = location / "current"
    assert sorted(path.name for path in current.iterdir()) == [
        "items.jsonl",
        "manifest.json",
    ]
    assert len((current / "items.jsonl").read_text().splitlines()) == 4
    assert list(json.loads((current / "manifest.json").read_text())["components"]) == [
        "items"
    ]


def _optional(**overrides: Any) -> ComponentSpec:
    optional = _items_spec(
        name="extra",
        output_file="extra.jsonl",
        critical=False,
        persist_raw=False,
        quality=None,
    )
    return replace(optional, **overrides)


OTHER_METADATA = replace(ItemsConnector.metadata, connector_id="other")


@pytest.mark.parametrize(
    ("specs", "store_overrides", "message"),
    [
        pytest.param(
            [_items_spec(critical=False)], {}, "exactly one critical", id="no-critical"
        ),
        pytest.param(
            [_items_spec(), _items_spec(name="two", output_file="two.jsonl")],
            {},
            "exactly one critical",
            id="two-critical",
        ),
        pytest.param(
            [_items_spec(), _optional(name="items")],
            {},
            "unique names",
            id="duplicate-name",
        ),
        pytest.param(
            [_items_spec(), _optional(output_file="ITEMS.jsonl")],
            {},
            "unique names",
            id="duplicate-file-casefold",
        ),
        pytest.param([_items_spec(name="-items")], {}, "unsafe name", id="bad-name"),
        pytest.param([_items_spec(name="con")], {}, "unsafe name", id="device-name"),
        pytest.param(
            [_items_spec(output_file="manifest.json")], {}, "unsafe name", id="reserved"
        ),
        pytest.param(
            [_items_spec(output_file="items.txt")], {}, "unsafe name", id="not-jsonl"
        ),
        pytest.param(
            [_items_spec(output_file="../items.jsonl")], {}, "unsafe name", id="path"
        ),
        pytest.param(
            [_items_spec(), _optional(sensitive=True, persist_raw=True)],
            {},
            "cannot persist raw",
            id="sensitive-with-raw",
        ),
        pytest.param(
            [_items_spec(sensitive=True, persist_raw=False)],
            {},
            "cannot be sensitive",
            id="sensitive-critical",
        ),
        pytest.param(
            [_items_spec(connector=None, unavailable="missing")],
            {},
            "must be available",
            id="critical-unavailable",
        ),
        pytest.param(
            [_items_spec(persist_raw=False)],
            {},
            "must persist raw",
            id="critical-without-raw",
        ),
        pytest.param(
            [_items_spec(), _optional(quality=QualityPolicy())],
            {},
            "quality policy",
            id="optional-quality",
        ),
        pytest.param(
            [_items_spec(), _optional(connector=None)],
            {},
            "connector or a reason",
            id="no-connector-reason",
        ),
        pytest.param(
            [_items_spec(metadata=OTHER_METADATA)],
            {},
            "metadata differs",
            id="metadata-mismatch",
        ),
        pytest.param(
            [_items_spec()], {"timezone": "Mars/Base"}, "timezone", id="timezone"
        ),
        pytest.param(
            [_items_spec()], {"store_id": "Items Store"}, "store_id", id="store-id"
        ),
        pytest.param(
            [_items_spec()],
            {"settings": {"path": Path("x")}},
            "JSON serializable",
            id="public-settings",
        ),
    ],
)
def test_invalid_compositions_fail_before_creating_output(
    tmp_path: Path,
    specs: list[ComponentSpec],
    store_overrides: dict[str, Any],
    message: str,
) -> None:
    store = FakeStore(specs=specs, **store_overrides)

    with pytest.raises(ValueError, match=message):
        _run(tmp_path, store)

    assert not (tmp_path / "out").exists()
