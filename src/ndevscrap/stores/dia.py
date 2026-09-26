"""DIA Argentina: VTEX catalog composed with the ClubDIA coupon feed."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..connectors.clubdia import ClubDiaConnector
from ..connectors.vtex import VtexConnector, VtexSettings
from ..contracts import ComponentSpec, Transport
from ..models import ProductSnapshot
from ..quality import QualityPolicy, valid_product
from ..session import JsonFileSessionProvider

DEFAULT_BASE_URL = "https://diaonline.supermercadosdia.com.ar"
BASE_URL_VARIABLE = "NDEVSCRAP_DIA_BASE_URL"
SESSION_VARIABLE = "NDEVSCRAP_DIA_SESSION_FILE"
MISSING_SESSION = f"Set {SESSION_VARIABLE} to include ClubDIA coupons"


@dataclass(frozen=True, slots=True)
class DiaSettings:
    vtex: VtexSettings
    session_file: Path | None = None
    country: str = "ARG"

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> DiaSettings:
        base_url = environ.get(BASE_URL_VARIABLE, "").strip() or DEFAULT_BASE_URL
        # The session is read only from the explicit variable, never from a
        # default location such as .secrets/.
        session_path = environ.get(SESSION_VARIABLE, "").strip()
        settings = cls(
            vtex=VtexSettings(base_url=base_url),
            session_file=Path(session_path) if session_path else None,
        )
        settings.vtex.validate()
        return settings


class DiaStore:
    store_id = "dia"
    platform = "vtex"
    timezone = "America/Argentina/Buenos_Aires"

    def __init__(self, settings: DiaSettings) -> None:
        self._settings = settings

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> DiaStore:
        return cls(DiaSettings.from_environment(environ))

    def validate(self) -> None:
        self._settings.vtex.validate()

    def public_settings(self) -> Mapping[str, Any]:
        return {
            "country": self._settings.country,
            "vtex": self._settings.vtex.public_settings(),
            "session_configured": self._settings.session_file is not None,
        }

    def components(self, transport: Transport) -> Sequence[ComponentSpec]:
        settings = self._settings
        clubdia = (
            ClubDiaConnector(
                settings.vtex.base_url,
                transport,
                JsonFileSessionProvider(settings.session_file),
            )
            if settings.session_file is not None
            else None
        )
        return (
            ComponentSpec(
                name="catalog",
                label="catalog",
                output_file="products.jsonl",
                metadata=VtexConnector.metadata,
                connector=VtexConnector(settings.vtex, transport),
                critical=True,
                persist_raw=True,
                validator=valid_product,
                record_key=_product_key,
                quality=QualityPolicy(),
            ),
            ComponentSpec(
                name="clubdia",
                label="ClubDIA",
                output_file="coupons.jsonl",
                metadata=ClubDiaConnector.metadata,
                connector=clubdia,
                critical=False,
                persist_raw=False,
                sensitive=True,
                unavailable=None if clubdia is not None else MISSING_SESSION,
            ),
        )


def _product_key(product: ProductSnapshot) -> tuple[str, str]:
    return (product.sku_id, product.seller_id)
