"""Typed runtime configuration."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class DiaConfig:
    postal_code: str
    output_dir: Path
    base_url: str = "https://diaonline.supermercadosdia.com.ar"
    locale: str = "es-AR"
    currency: str = "ARS"
    country: str = "ARG"
    timezone: str = "America/Argentina/Buenos_Aires"
    sales_channel: int = 1
    page_size: int = 50
    timeout_seconds: float = 20.0
    requests_per_second: float = 1.0
    max_retries: int = 3
    session_file: Path | None = None
    contact: str | None = None

    def validate(self) -> None:
        if not self.postal_code.strip():
            raise ValueError("postal_code is required")
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTPS URL")
        if not 1 <= self.page_size <= 50:
            raise ValueError("page_size must be between 1 and 50")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        if not 0 <= self.max_retries <= 10:
            raise ValueError("max_retries must be between 0 and 10")

    @classmethod
    def from_environment(cls, postal_code: str, output_dir: Path) -> DiaConfig:
        session_path = os.getenv("NDEVSCRAP_DIA_SESSION_FILE")
        return cls(
            postal_code=postal_code,
            output_dir=output_dir,
            base_url=os.getenv(
                "NDEVSCRAP_DIA_BASE_URL",
                "https://diaonline.supermercadosdia.com.ar",
            ).rstrip("/"),
            session_file=Path(session_path) if session_path else None,
            contact=os.getenv("NDEVSCRAP_CONTACT"),
        )

    def public_hash(self) -> str:
        values = asdict(self)
        values["output_dir"] = str(self.output_dir)
        values["session_file"] = bool(self.session_file)
        canonical = json.dumps(values, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
