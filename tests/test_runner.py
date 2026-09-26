from __future__ import annotations

import gzip
import hashlib
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from ndevscrap.config import DiaConfig
from ndevscrap.contracts import HttpRequest, HttpResponse, RunContext
from ndevscrap.runner import _run_clubdia, run_dia
from ndevscrap.transport import HttpStatusError, TransportError

FIXTURES = Path(__file__).parent / "fixtures"
BASE_URL = "https://shop.example"
POSTAL_CODE = "1806"
PAGE_SIZE = 5
SNAPSHOT_DATE = "2026-09-26"
TREE_PATH = "/api/catalog_system/pub/category/tree/3"
COOKIE_SENTINEL = "cookie-SENTINEL-value"
ORDER_FORM_SENTINEL = "order-form-SENTINEL-value"
TOKEN_SENTINEL = "token-SENTINEL-value"
SENTINELS = (COOKIE_SENTINEL, ORDER_FORM_SENTINEL, TOKEN_SENTINEL)


class ExpiredSessionTransport:
    retries = 0

    def request(self, request):
        raise HttpStatusError(401, request.url)


class StoreTransport:
    """Route requests to deterministic VTEX and ClubDIA payloads.

    Product payloads follow the shape of ``tests/fixtures/vtex/product_page.json``
    and are generated so that volume can be scaled per scenario.
    """

    def __init__(
        self,
        products: int,
        *,
        clubdia: str = "ok",
        partitions: tuple[str, ...] = ("almacen",),
    ) -> None:
        self.products = products
        self.clubdia = clubdia
        self.partitions = partitions
        self.retries = 0
        self.requests: list[tuple[str, int | None]] = []
        self.page_hooks: dict[tuple[str, int], Callable[[], object]] = {}
        self.token_retries = 0

    def request(self, request: HttpRequest) -> HttpResponse:
        path = request.url.removeprefix(BASE_URL)
        page = request.params.get("page")
        self.requests.append((path, page if isinstance(page, int) else None))
        if path == TREE_PATH:
            tree = [
                {"url": f"{BASE_URL}/{slug}", "children": []}
                for slug in self.partitions
            ]
            return _json(request, tree)
        if path.startswith("/api/intelligent-search/v1/product-search/"):
            assert isinstance(page, int)
            slug = path.rsplit("/", 1)[-1]
            hook = self.page_hooks.get((slug, page))
            if hook is not None:
                return _json(request, hook())
            offset = self.partitions.index(slug) * 1000
            return _json(request, _page(self.products, page, offset))
        if path.endswith("/token-by-user"):
            self.retries += self.token_retries
            return self._clubdia_token(request)
        if path.endswith("/cupons"):
            payload = json.loads(
                (FIXTURES / "clubdia" / "coupons.json").read_text(encoding="utf-8")
            )
            return _json(request, payload)
        raise AssertionError(f"unexpected request {request.url}")

    def _clubdia_token(self, request: HttpRequest) -> HttpResponse:
        if self.clubdia == "expired":
            raise HttpStatusError(401, request.url)
        if self.clubdia == "chained":
            try:
                raise ValueError(f"header rejected: {COOKIE_SENTINEL}")
            except ValueError as cause:
                raise TransportError("HTTP request failed after retries") from cause
        if self.clubdia == "chained-unexpected":
            try:
                raise ValueError(f"header rejected: {COOKIE_SENTINEL}")
            except ValueError as cause:
                raise KeyError("unexpected failure") from cause
        if self.clubdia == "unexpected":
            raise KeyError(f"unexpected {ORDER_FORM_SENTINEL}")
        if self.clubdia == "no-token":
            return _json(request, {"message": TOKEN_SENTINEL})
        return _json(request, {"tokenClubDia": TOKEN_SENTINEL})

    def search_requests(self) -> list[tuple[str, int]]:
        return [
            (path.rsplit("/", 1)[-1], page)
            for path, page in self.requests
            if page is not None
        ]

    def page_requests(self) -> list[int]:
        return [page for _, page in self.search_requests()]


def _json(request: HttpRequest, payload: object) -> HttpResponse:
    return HttpResponse(200, request.url, {}, json.dumps(payload).encode())


def _product(index: int) -> dict[str, object]:
    return {
        "productId": f"product-{index}",
        "productName": f"Producto {index}",
        "brand": "Marca",
        "categories": ["/Almacén/"],
        "link": f"{BASE_URL}/producto-{index}/p",
        "items": [
            {
                "itemId": f"sku-{index}",
                "ean": f"77900000{index:05d}",
                "nameComplete": f"Producto {index} 500 g",
                "images": [],
                "sellers": [
                    {
                        "sellerId": "1",
                        "sellerName": "Vendedor",
                        "sellerDefault": True,
                        "commertialOffer": {
                            "AvailableQuantity": 3,
                            "IsAvailable": True,
                            "ListPrice": 120.5,
                            "Price": 100.25,
                        },
                    }
                ],
            }
        ],
    }


def _page(total: int, page: int, offset: int = 0) -> dict[str, object]:
    first = (page - 1) * PAGE_SIZE
    indexes = range(first, min(first + PAGE_SIZE, total))
    return {
        "products": [_product(offset + index) for index in indexes],
        "recordsFiltered": total,
    }


def _session_file(tmp_path: Path, mode: str) -> Path | None:
    if mode == "none":
        return None
    path = tmp_path / "session.json"
    if mode == "malformed":
        path.write_text(
            f'{{"cookies": {{"vtex_session": "{COOKIE_SENTINEL}"', encoding="utf-8"
        )
        return path
    headers = {} if mode == "no-order-form" else {"order-form-id": ORDER_FORM_SENTINEL}
    path.write_text(
        json.dumps({"headers": headers, "cookies": {"vtex_session": COOKIE_SENTINEL}}),
        encoding="utf-8",
    )
    return path


def _config(tmp_path: Path, *, session: str = "valid") -> DiaConfig:
    return DiaConfig(
        postal_code=POSTAL_CODE,
        output_dir=tmp_path / "out",
        base_url=BASE_URL,
        page_size=PAGE_SIZE,
        session_file=_session_file(tmp_path, session),
    )


_CLOCK_TICKS: dict[Path, int] = {}


def _clock_for(tmp_path: Path) -> Callable[[], datetime]:
    """Advance one minute per call within the same local day for each test."""

    def clock() -> datetime:
        tick = _CLOCK_TICKS.get(tmp_path, 0)
        _CLOCK_TICKS[tmp_path] = tick + 1
        start = datetime(
            2026, 9, 26, 10, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires")
        )
        return start + timedelta(minutes=tick)

    return clock


def _run(tmp_path: Path, transport: StoreTransport, *, session: str = "valid"):
    return run_dia(
        _config(tmp_path, session=session),
        transport=transport,
        clock=_clock_for(tmp_path),
    )


def _location(tmp_path: Path) -> Path:
    return (tmp_path / "out" / "dia" / POSTAL_CODE).resolve()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        digest.update(path.relative_to(root).as_posix().encode())
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _index(tmp_path: Path) -> dict:
    path = _location(tmp_path) / "current" / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _assert_current_provenance(tmp_path: Path) -> None:
    location = _location(tmp_path)
    index = _index(tmp_path)
    assert index["kind"] == "current-index"
    for entry in index["components"].values():
        current_file = location / "current" / entry["file"]
        assert _sha256(current_file) == entry["sha256"]
        assert _rows(current_file) == entry["records"]
        if entry["provenance"] != "run":
            assert entry["source"] is None
            continue
        source = location / entry["source"]
        assert _sha256(source) == entry["sha256"]
        run_manifest = json.loads(
            (source.parent.parent / "manifest.json").read_text(encoding="utf-8")
        )
        assert run_manifest["run_id"] == entry["run_id"]


def _all_output_text(root: Path) -> str:
    chunks: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        data = path.read_bytes()
        if path.suffix == ".gz":
            data = gzip.decompress(data)
        chunks.append(data.decode("utf-8", errors="replace"))
    return "\n".join(chunks)


def _exhausted(transport: StoreTransport, retries: int = 0) -> Callable[[], object]:
    def hook() -> object:
        transport.retries += retries
        raise HttpStatusError(503, f"{BASE_URL}/search")

    return hook


def test_expired_clubdia_session_is_component_failure(tmp_path: Path) -> None:
    session = tmp_path / "session.json"
    session.write_text(json.dumps({"cookies": {"session": "secret"}}))
    config = DiaConfig(
        postal_code="1000",
        output_dir=tmp_path,
        session_file=session,
        base_url="https://shop.example",
    )
    context = RunContext("run", "dia", "1000", datetime(2026, 9, 23, tzinfo=UTC))

    coupons, result = _run_clubdia(config, context, ExpiredSessionTransport())

    assert coupons is None
    assert result.status == "authentication_required"
    assert "secret" not in repr(result.to_dict())


def test_missing_clubdia_session_is_actionable(tmp_path: Path) -> None:
    config = DiaConfig(postal_code="1806", output_dir=tmp_path)
    context = RunContext("run", "dia", "1806", datetime(2026, 9, 25, tzinfo=UTC))

    coupons, result = _run_clubdia(config, context, ExpiredSessionTransport())

    assert coupons is None
    assert result.status == "authentication_required"
    assert "NDEVSCRAP_DIA_SESSION_FILE" in result.errors[0]


def test_successful_run_publishes_current_with_verifiable_provenance(
    tmp_path: Path,
) -> None:
    manifest, destination = _run(tmp_path, StoreTransport(20))

    assert manifest.status == "success"
    assert destination == _location(tmp_path) / SNAPSHOT_DATE
    catalog = _index(tmp_path)["components"]["catalog"]
    assert catalog["run_id"] == manifest.run_id
    assert catalog["records"] == 20
    assert catalog["source"] == f"{SNAPSHOT_DATE}/normalized/products.jsonl"
    assert _index(tmp_path)["last_attempt"]["run_id"] == manifest.run_id
    _assert_current_provenance(tmp_path)


def test_quarantined_runs_do_not_poison_the_volume_baseline(tmp_path: Path) -> None:
    first, _ = _run(tmp_path, StoreTransport(20))
    location = _location(tmp_path)
    accepted_products = _sha256(location / "current" / "products.jsonl")
    accepted_snapshot = _tree_hash(location / SNAPSHOT_DATE)

    second, second_path = _run(tmp_path, StoreTransport(11))
    third, third_path = _run(tmp_path, StoreTransport(11))

    for manifest, path in ((second, second_path), (third, third_path)):
        assert manifest.components["catalog"].status == "quality_failure"
        assert "from 20" in manifest.components["catalog"].errors[0]
        assert path == location / "attempts" / SNAPSHOT_DATE / manifest.run_id
        assert (path / "manifest.json").exists()
        assert (path / "normalized" / "products.jsonl").exists()
    assert _sha256(location / "current" / "products.jsonl") == accepted_products
    assert _tree_hash(location / SNAPSHOT_DATE) == accepted_snapshot
    catalog = _index(tmp_path)["components"]["catalog"]
    assert catalog["run_id"] == first.run_id
    assert _index(tmp_path)["last_attempt"]["run_id"] == third.run_id
    _assert_current_provenance(tmp_path)


def test_failed_reruns_leave_the_accepted_snapshot_untouched(tmp_path: Path) -> None:
    _run(tmp_path, StoreTransport(20))
    location = _location(tmp_path)
    accepted_snapshot = _tree_hash(location / SNAPSHOT_DATE)

    transient = StoreTransport(20)
    transient.page_hooks[("almacen", 3)] = _exhausted(transient)
    structural = StoreTransport(20)
    # Pages 1-2 are resumed from the transient staging; page 3 is fetched again.
    structural.page_hooks[("almacen", 3)] = lambda: {"unexpected": True}
    transient_run, transient_path = _run(tmp_path, transient)
    structural_run, structural_path = _run(tmp_path, structural)

    assert (
        transient_path == location / "attempts" / SNAPSHOT_DATE / transient_run.run_id
    )
    assert structural_path == (
        location / "attempts" / SNAPSHOT_DATE / structural_run.run_id
    )
    assert _tree_hash(location / SNAPSHOT_DATE) == accepted_snapshot
    _assert_current_provenance(tmp_path)


def test_zero_products_are_quarantined(tmp_path: Path) -> None:
    manifest, destination = _run(tmp_path, StoreTransport(0))

    location = _location(tmp_path)
    assert manifest.status == "failed"
    assert manifest.components["catalog"].status == "quality_failure"
    assert destination == location / "attempts" / SNAPSHOT_DATE / manifest.run_id
    assert not (location / SNAPSHOT_DATE).exists()
    assert not (location / "current" / "products.jsonl").exists()
    clubdia = _index(tmp_path)["components"]["clubdia"]
    assert clubdia["source"].startswith(f"attempts/{SNAPSHOT_DATE}/{manifest.run_id}/")
    _assert_current_provenance(tmp_path)


def test_accepted_rerun_archives_previous_snapshot_and_keeps_coupon_source(
    tmp_path: Path,
) -> None:
    first, _ = _run(tmp_path, StoreTransport(20))
    second, _ = _run(tmp_path, StoreTransport(20, clubdia="expired"))
    third, _ = _run(tmp_path, StoreTransport(20, clubdia="expired"))

    location = _location(tmp_path)
    archived = location / "attempts" / SNAPSHOT_DATE / first.run_id
    assert second.status == "partial_success"
    assert json.loads((archived / "manifest.json").read_text())["run_id"] == (
        first.run_id
    )
    assert (location / "attempts" / SNAPSHOT_DATE / second.run_id).exists()
    components = _index(tmp_path)["components"]
    assert components["catalog"]["run_id"] == third.run_id
    assert components["clubdia"]["run_id"] == first.run_id
    assert components["clubdia"]["source"] == (
        f"attempts/{SNAPSHOT_DATE}/{first.run_id}/normalized/coupons.jsonl"
    )
    assert not (location / SNAPSHOT_DATE / "normalized" / "coupons.jsonl").exists()
    _assert_current_provenance(tmp_path)


def test_transient_failure_keeps_staging_and_resumes_confirmed_pages(
    tmp_path: Path,
) -> None:
    partitions = ("almacen", "bebidas")
    failing = StoreTransport(20, partitions=partitions)
    failing.page_hooks[("bebidas", 4)] = _exhausted(failing, retries=3)
    failed, failed_path = _run(tmp_path, failing)

    location = _location(tmp_path)
    staging = location / f".staging-{SNAPSHOT_DATE}"
    assert failed.components["catalog"].status == "failed"
    assert failed.components["catalog"].retries == 3
    assert failed_path == location / "attempts" / SNAPSHOT_DATE / failed.run_id
    assert (failed_path / "manifest.json").exists()
    assert (failed_path / "normalized" / "coupons.jsonl").exists()
    assert (staging / "raw" / "catalog" / "bebidas-page-003.json.gz").exists()
    assert not (location / SNAPSHOT_DATE).exists()

    resumed = StoreTransport(20, clubdia="expired", partitions=partitions)
    manifest, destination = _run(tmp_path, resumed)

    assert manifest.status == "partial_success"
    assert destination == location / SNAPSHOT_DATE
    assert (TREE_PATH, None) in resumed.requests
    assert resumed.search_requests() == [
        ("almacen", 1),
        ("bebidas", 1),
        ("bebidas", 4),
    ]
    assert _rows(location / "current" / "products.jsonl") == 40
    assert not (destination / "normalized" / "coupons.jsonl").exists()
    assert not staging.exists()
    _assert_current_provenance(tmp_path)


def test_structural_failure_is_kept_as_evidence_and_refetched(tmp_path: Path) -> None:
    broken = StoreTransport(20)
    broken.page_hooks[("almacen", 3)] = lambda: {"unexpected": True}
    failed, failed_path = _run(tmp_path, broken)

    location = _location(tmp_path)
    assert failed.components["catalog"].status == "failed"
    assert failed_path == location / "attempts" / SNAPSHOT_DATE / failed.run_id
    assert (failed_path / "rejected" / "catalog" / "almacen-page-003.json.gz").exists()
    assert not (failed_path / "raw" / "catalog" / "almacen-page-003.json.gz").exists()
    assert not (location / f".staging-{SNAPSHOT_DATE}").exists()

    retry = StoreTransport(20)
    manifest, _ = _run(tmp_path, retry)

    assert manifest.status == "success"
    assert retry.page_requests() == [1, 2, 3, 4]


def test_truncated_raw_page_is_fetched_again(tmp_path: Path) -> None:
    failing = StoreTransport(20)

    def exhausted() -> object:
        raise TransportError("HTTP request failed after retries")

    failing.page_hooks[("almacen", 3)] = exhausted
    _run(tmp_path, failing)
    staged = (
        _location(tmp_path)
        / f".staging-{SNAPSHOT_DATE}"
        / "raw"
        / "catalog"
        / "almacen-page-002.json.gz"
    )
    staged.write_bytes(staged.read_bytes()[:10])

    retry = StoreTransport(20)
    manifest, _ = _run(tmp_path, retry)

    assert manifest.status == "success"
    assert retry.page_requests() == [1, 2, 3, 4]


@pytest.mark.parametrize(
    ("clubdia", "session"),
    [("expired", "valid"), ("ok", "none"), ("unexpected", "valid")],
)
def test_clubdia_failures_do_not_affect_a_valid_catalog(
    tmp_path: Path, clubdia: str, session: str
) -> None:
    first, _ = _run(tmp_path, StoreTransport(20))
    coupons = _sha256(_location(tmp_path) / "current" / "coupons.jsonl")
    baseline = first.components["catalog"]

    manifest, destination = _run(
        tmp_path, StoreTransport(20, clubdia=clubdia), session=session
    )

    catalog = manifest.components["catalog"]
    assert manifest.status == "partial_success"
    assert catalog.status == "success"
    assert (catalog.discovered, catalog.normalized, catalog.rejected) == (
        baseline.discovered,
        baseline.normalized,
        baseline.rejected,
    )
    assert catalog.retries == 0
    assert destination == _location(tmp_path) / SNAPSHOT_DATE
    assert _sha256(_location(tmp_path) / "current" / "coupons.jsonl") == coupons
    components = _index(tmp_path)["components"]
    assert components["catalog"]["run_id"] == manifest.run_id
    assert components["clubdia"]["run_id"] == first.run_id
    _assert_current_provenance(tmp_path)


def test_clubdia_success_is_published_when_catalog_fails(tmp_path: Path) -> None:
    first, _ = _run(tmp_path, StoreTransport(20))
    broken = StoreTransport(20)
    broken.page_hooks[("almacen", 2)] = lambda: {"unexpected": True}

    manifest, destination = _run(tmp_path, broken)

    assert manifest.status == "failed"
    assert manifest.components["clubdia"].status == "success"
    components = _index(tmp_path)["components"]
    assert components["catalog"]["run_id"] == first.run_id
    assert components["clubdia"]["run_id"] == manifest.run_id
    assert components["clubdia"]["source"] == (
        f"attempts/{SNAPSHOT_DATE}/{manifest.run_id}/normalized/coupons.jsonl"
    )
    assert destination.name == manifest.run_id
    _assert_current_provenance(tmp_path)


def test_retries_are_attributed_to_each_component(tmp_path: Path) -> None:
    transport = StoreTransport(20)

    def retried_page() -> object:
        transport.retries += 2
        return _page(20, 2)

    transport.page_hooks[("almacen", 2)] = retried_page
    transport.token_retries = 1

    manifest, _ = _run(tmp_path, transport)

    assert manifest.components["catalog"].retries == 2
    assert manifest.components["clubdia"].retries == 1


@pytest.mark.parametrize(
    ("clubdia", "session", "expected_error"),
    [
        ("ok", "valid", None),
        ("expired", "valid", "ClubDIA session rejected with HTTP 401"),
        ("chained", "valid", "TransportError: ClubDIA request failed"),
        ("unexpected", "valid", "KeyError: unexpected ClubDIA failure"),
        ("chained-unexpected", "valid", "KeyError: unexpected ClubDIA failure"),
        (
            "no-token",
            "valid",
            "ClubDiaAuthenticationError: ClubDIA session unavailable or rejected",
        ),
        (
            "ok",
            "no-order-form",
            "ClubDiaAuthenticationError: ClubDIA session unavailable or rejected",
        ),
        (
            "ok",
            "malformed",
            "SessionConfigurationError: ClubDIA session unavailable or rejected",
        ),
    ],
)
def test_session_material_never_reaches_output_or_logs(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    clubdia: str,
    session: str,
    expected_error: str | None,
) -> None:
    caplog.set_level(logging.DEBUG)

    manifest, _ = _run(tmp_path, StoreTransport(20, clubdia=clubdia), session=session)

    assert manifest.components["catalog"].status == "success"
    assert manifest.components["clubdia"].errors == (
        [] if expected_error is None else [expected_error]
    )
    output = _all_output_text(tmp_path / "out")
    for sentinel in SENTINELS:
        assert sentinel not in output
    assert "SENTINEL" not in caplog.text
