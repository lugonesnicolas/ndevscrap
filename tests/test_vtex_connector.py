from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from ndevscrap.config import DiaConfig
from ndevscrap.connectors.vtex import (
    CatalogCompletenessError,
    VtexConnector,
    _category_nodes,
)
from ndevscrap.contracts import HttpResponse, RawRecord, RunContext

FIXTURES = Path(__file__).parent / "fixtures" / "vtex"


class UnusedTransport:
    retries = 0

    def request(self, request):  # pragma: no cover - normalization does not call it
        raise AssertionError("transport was not expected")


class FakeTransport:
    def __init__(self, payloads: list[object]) -> None:
        self.payloads = payloads
        self.requests = []
        self.retries = 0

    def request(self, request):
        self.requests.append(request)
        payload = self.payloads.pop(0)
        return HttpResponse(
            status_code=200,
            url=request.url,
            headers={},
            body=json.dumps(payload).encode(),
        )


def test_normalizes_skus_with_exact_prices(tmp_path: Path) -> None:
    payload = json.loads((FIXTURES / "product_page.json").read_text(encoding="utf-8"))
    captured = datetime(2026, 9, 23, 12, tzinfo=UTC)
    connector = VtexConnector(
        DiaConfig(postal_code="1000", output_dir=tmp_path), UnusedTransport()
    )
    record = RawRecord(
        key="almacen:page-001",
        source_url="https://shop.example/search?page=1",
        payload=payload,
        fetched_at=captured,
    )

    products = tuple(
        connector.normalize(
            record,
            RunContext("run", "dia", "1000", captured),
        )
    )

    assert len(products) == 2
    assert products[0].sku_id == "sku-1"
    assert products[0].selling_price == Decimal("1100.5")
    assert products[0].list_price == Decimal("1389.0")
    assert products[0].promotion == "Oferta pública"
    assert products[0].postal_code == "1000"
    assert products[1].available is False


def test_category_tree_preserves_slug_paths() -> None:
    payload = json.loads((FIXTURES / "category_tree.json").read_text(encoding="utf-8"))

    nodes = _category_nodes(payload)

    assert nodes[0].slug_path == ("almacen",)
    assert nodes[0].children[0].slug_path == ("almacen", "conservas")


def test_discovery_builds_every_page_with_location_context(tmp_path: Path) -> None:
    tree = json.loads((FIXTURES / "category_tree.json").read_text(encoding="utf-8"))
    page = {"products": [], "recordsFiltered": 101}
    transport = FakeTransport([tree, page])
    connector = VtexConnector(
        DiaConfig(postal_code="1000", output_dir=tmp_path), transport
    )
    context = RunContext("run", "dia", "1000", datetime(2026, 9, 23, tzinfo=UTC))

    items = list(connector.discover(context))

    assert [item.key for item in items] == [
        "category-tree",
        "almacen:page-001",
        "almacen:page-002",
        "almacen:page-003",
    ]
    assert items[-1].request.params["zip-code"] == "1000"
    assert items[-1].request.params["page"] == 3


def test_discovery_refuses_truncated_leaf_partition(tmp_path: Path) -> None:
    tree = [
        {
            "url": "https://shop.example/oversized",
            "children": [],
        }
    ]
    transport = FakeTransport([tree, {"products": [], "recordsFiltered": 2501}])
    connector = VtexConnector(
        DiaConfig(postal_code="1000", output_dir=tmp_path), transport
    )
    context = RunContext("run", "dia", "1000", datetime(2026, 9, 23, tzinfo=UTC))

    with pytest.raises(CatalogCompletenessError, match="above the safe capacity"):
        list(connector.discover(context))
