"""Reusable VTEX Intelligent Search connector."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse, urlsplit

from ..contracts import (
    ConnectorMetadata,
    HttpRequest,
    RawRecord,
    RunContext,
    SourceItem,
    Transport,
)
from ..models import ProductSnapshot
from ..transport import https_origin


class CatalogCompletenessError(RuntimeError):
    """Raised rather than returning a truncated search result."""


@dataclass(frozen=True, slots=True)
class VtexSettings:
    """Platform configuration for one VTEX storefront.

    The location (postal code) comes from the run context, not from here.
    """

    base_url: str
    locale: str = "es-AR"
    currency: str = "ARS"
    sales_channel: int = 1
    page_size: int = 50
    max_pages: int = 50

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", self.base_url.strip().removesuffix("/"))

    def validate(self) -> None:
        parts = urlsplit(self.base_url)
        if (
            https_origin(self.base_url) is None
            or parts.scheme != "https"
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.path
            or parts.query
            or parts.fragment
            or "?" in self.base_url
            or "#" in self.base_url
        ):
            raise ValueError(
                "base_url must be an HTTPS origin without credentials, path, "
                "query or fragment"
            )
        if not 1 <= self.page_size <= 50:
            raise ValueError("page_size must be between 1 and 50")
        if not 1 <= self.max_pages <= 50:
            raise ValueError("max_pages must be between 1 and 50")

    def public_settings(self) -> dict[str, str | int]:
        return {
            "base_url": self.base_url,
            "locale": self.locale,
            "currency": self.currency,
            "sales_channel": self.sales_channel,
            "page_size": self.page_size,
            "max_pages": self.max_pages,
        }


@dataclass(frozen=True, slots=True)
class CategoryNode:
    slug_path: tuple[str, ...]
    children: tuple[CategoryNode, ...]


class VtexConnector:
    metadata = ConnectorMetadata(
        connector_id="vtex-intelligent-search",
        version="1.0.0",
        owner="maintainers",
        access_method="api",
        schema_version="1",
    )

    def __init__(self, settings: VtexSettings, transport: Transport) -> None:
        self._settings = settings
        self._transport = transport
        self._search_url = (
            f"{settings.base_url}/api/intelligent-search/v1/product-search"
        )
        self._categories_url = (
            f"{settings.base_url}/api/catalog_system/pub/category/tree/3"
        )

    def discover(self, context: RunContext) -> Iterable[SourceItem]:
        category_response = self._transport.request(
            HttpRequest(method="GET", url=self._categories_url)
        )
        category_record = RawRecord(
            key="category-tree",
            source_url=category_response.url,
            payload=category_response.json(),
            fetched_at=datetime.now(UTC),
        )
        yield SourceItem(
            key="category-tree",
            request=HttpRequest(method="GET", url=self._categories_url),
            prefetched=category_record,
        )

        seen_partitions: set[tuple[str, ...]] = set()
        for node in _category_nodes(category_record.payload):
            if node.slug_path in seen_partitions:
                continue
            seen_partitions.add(node.slug_path)
            yield from self._discover_partition(node, context)

    def _discover_partition(
        self, node: CategoryNode, context: RunContext
    ) -> Iterable[SourceItem]:
        first_request = self._page_request(node.slug_path, 1, context)
        first_response = self._transport.request(first_request)
        first_record = RawRecord(
            key=_page_key(node.slug_path, 1),
            source_url=first_response.url,
            payload=first_response.json(),
            fetched_at=datetime.now(UTC),
        )
        total = _integer(first_record.payload.get("recordsFiltered"))
        capacity = self._settings.page_size * self._settings.max_pages
        if total > capacity:
            yield SourceItem(
                key=f"probe:{_partition_name(node.slug_path)}",
                request=first_request,
                prefetched=RawRecord(
                    key=f"probe:{_partition_name(node.slug_path)}",
                    source_url=first_record.source_url,
                    payload=first_record.payload,
                    fetched_at=first_record.fetched_at,
                ),
            )
            if not node.children:
                raise CatalogCompletenessError(
                    f"partition {_partition_name(node.slug_path)} contains {total} "
                    f"products, above the safe capacity of {capacity}"
                )
            for child in node.children:
                yield from self._discover_partition(child, context)
            return

        yield SourceItem(
            key=first_record.key,
            request=first_request,
            prefetched=first_record,
        )
        pages = math.ceil(total / self._settings.page_size)
        for page in range(2, pages + 1):
            yield SourceItem(
                key=_page_key(node.slug_path, page),
                request=self._page_request(node.slug_path, page, context),
            )

    def _page_request(
        self, slug_path: tuple[str, ...], page: int, context: RunContext
    ) -> HttpRequest:
        facets = "/".join(
            value
            for level, slug in enumerate(slug_path, start=1)
            for value in (f"category-{level}", slug)
        )
        return HttpRequest(
            method="GET",
            url=f"{self._search_url}/{facets}",
            params={
                "page": page,
                "count": self._settings.page_size,
                "locale": self._settings.locale,
                "sc": self._settings.sales_channel,
                "zip-code": context.postal_code,
                "hideUnavailableItems": "false",
            },
        )

    def extract(self, item: SourceItem, context: RunContext) -> RawRecord:
        if item.prefetched is not None:
            return item.prefetched
        response = self._transport.request(item.request)
        return RawRecord(
            key=item.key,
            source_url=response.url,
            payload=response.json(),
            fetched_at=datetime.now(UTC),
        )

    def normalize(
        self, record: RawRecord, context: RunContext
    ) -> Iterable[ProductSnapshot]:
        if record.key == "category-tree" or record.key.startswith("probe:"):
            return ()
        payload = record.payload
        if not isinstance(payload, dict) or not isinstance(
            payload.get("products"), list
        ):
            raise TypeError(f"unexpected VTEX payload for {record.key}")
        snapshots: list[ProductSnapshot] = []
        for product in payload["products"]:
            snapshots.extend(self._normalize_product(product, record, context))
        return snapshots

    def _normalize_product(
        self,
        product: Mapping[str, Any],
        record: RawRecord,
        context: RunContext,
    ) -> list[ProductSnapshot]:
        result: list[ProductSnapshot] = []
        items = product.get("items")
        if not isinstance(items, list):
            return result
        for item in items:
            if not isinstance(item, dict):
                continue
            seller = _default_seller(item.get("sellers"))
            if seller is None:
                continue
            offer = seller.get("commertialOffer")
            if not isinstance(offer, dict):
                continue
            price = _decimal(offer.get("Price"))
            quantity = _integer(offer.get("AvailableQuantity"))
            available = bool(
                offer.get("IsAvailable", quantity > 0 and price is not None)
            )
            result.append(
                ProductSnapshot(
                    product_id=str(product.get("productId", "")),
                    sku_id=str(item.get("itemId", "")),
                    gtin=_optional_string(item.get("ean")),
                    name=str(
                        item.get("nameComplete") or product.get("productName") or ""
                    ),
                    brand=str(product.get("brand") or ""),
                    categories=_string_tuple(product.get("categories")),
                    product_url=_product_url(self._settings.base_url, product),
                    image_urls=_image_urls(item.get("images")),
                    seller_id=str(seller.get("sellerId") or ""),
                    seller_name=str(seller.get("sellerName") or ""),
                    available=available,
                    available_quantity=quantity,
                    list_price=_decimal(offer.get("ListPrice")),
                    selling_price=price,
                    currency=self._settings.currency,
                    postal_code=context.postal_code,
                    captured_at=context.captured_at,
                    source_url=record.source_url,
                    promotion=_promotion(offer),
                )
            )
        return result


def _category_nodes(payload: Any) -> tuple[CategoryNode, ...]:
    if not isinstance(payload, list):
        raise TypeError("VTEX category tree must be a list")
    nodes: list[CategoryNode] = []
    for value in payload:
        node = _category_node(value, ())
        if node is not None:
            nodes.append(node)
    return tuple(nodes)


def _category_node(value: Any, parent: tuple[str, ...]) -> CategoryNode | None:
    if not isinstance(value, dict):
        return None
    path = urlparse(str(value.get("url") or "")).path.strip("/")
    slugs = tuple(part for part in path.split("/") if part)
    slug_path = slugs if slugs else parent
    if not slug_path:
        return None
    raw_children = value.get("children")
    children = (
        tuple(
            child
            for item in raw_children
            if (child := _category_node(item, slug_path)) is not None
        )
        if isinstance(raw_children, list)
        else ()
    )
    return CategoryNode(slug_path=slug_path, children=children)


def _default_seller(value: Any) -> Mapping[str, Any] | None:
    if not isinstance(value, list):
        return None
    sellers = [seller for seller in value if isinstance(seller, dict)]
    return next(
        (seller for seller in sellers if seller.get("sellerDefault")), None
    ) or (sellers[0] if sellers else None)


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _optional_string(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if item not in (None, ""))


def _image_urls(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        str(image["imageUrl"])
        for image in value
        if isinstance(image, dict) and image.get("imageUrl")
    )


def _product_url(base_url: str, product: Mapping[str, Any]) -> str:
    link = str(product.get("link") or "")
    if link.startswith(("http://", "https://")):
        return link
    slug = str(product.get("linkText") or "").strip("/")
    return f"{base_url}/{slug}/p" if slug else base_url


def _promotion(offer: Mapping[str, Any]) -> str | None:
    for key in ("discountHighlights", "DiscountHighLight", "teasers", "Teasers"):
        entries = offer.get(key)
        if not isinstance(entries, list):
            continue
        names = [
            str(entry.get("name") or entry.get("<Name>") or "").strip()
            for entry in entries
            if isinstance(entry, dict)
        ]
        names = [name for name in names if name]
        if names:
            return " | ".join(names)
    return None


def _partition_name(slug_path: tuple[str, ...]) -> str:
    return "/".join(slug_path)


def _page_key(slug_path: tuple[str, ...], page: int) -> str:
    return f"{_partition_name(slug_path)}:page-{page:03d}"
