"""Typed runtime configuration shared by every store."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

TIMEOUT_VARIABLE = "NDEVSCRAP_HTTP_TIMEOUT_SECONDS"
RATE_VARIABLE = "NDEVSCRAP_HTTP_REQUESTS_PER_SECOND"
RETRIES_VARIABLE = "NDEVSCRAP_HTTP_MAX_RETRIES"
RETRY_AFTER_VARIABLE = "NDEVSCRAP_HTTP_MAX_RETRY_AFTER_SECONDS"
CONTACT_VARIABLE = "NDEVSCRAP_CONTACT"
_INTEGER = re.compile(r"-?[0-9]+")
_PRINTABLE_ASCII = re.compile(r"[\x20-\x7e]*")
_MAX_CONTACT_LENGTH = 200


@dataclass(frozen=True, slots=True)
class HttpSettings:
    timeout_seconds: float = 20.0
    requests_per_second: float = 1.0
    max_retries: int = 3
    max_retry_after_seconds: float = 120.0

    def validate(self) -> None:
        _check_range(TIMEOUT_VARIABLE, self.timeout_seconds, 0, 300)
        _check_range(RATE_VARIABLE, self.requests_per_second, 0, 2)
        if not 0 <= self.max_retries <= 10:
            raise ValueError(f"{RETRIES_VARIABLE} must be an integer in [0, 10]")
        _check_range(RETRY_AFTER_VARIABLE, self.max_retry_after_seconds, 0, 3600)

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> HttpSettings:
        defaults = cls()
        settings = cls(
            timeout_seconds=_float(environ, TIMEOUT_VARIABLE, defaults.timeout_seconds),
            requests_per_second=_float(
                environ, RATE_VARIABLE, defaults.requests_per_second
            ),
            max_retries=_integer(environ, RETRIES_VARIABLE, defaults.max_retries),
            max_retry_after_seconds=_float(
                environ, RETRY_AFTER_VARIABLE, defaults.max_retry_after_seconds
            ),
        )
        settings.validate()
        return settings


@dataclass(frozen=True, slots=True)
class RunSettings:
    postal_code: str
    output_dir: Path
    contact: str | None = None

    def validate(self) -> None:
        if not self.postal_code.strip():
            raise ValueError("postal_code is required")
        if self.contact is not None and (
            len(self.contact) > _MAX_CONTACT_LENGTH
            or not _PRINTABLE_ASCII.fullmatch(self.contact)
        ):
            raise ValueError(
                f"{CONTACT_VARIABLE} must be printable ASCII of at most "
                f"{_MAX_CONTACT_LENGTH} characters"
            )

    @classmethod
    def from_environment(
        cls, postal_code: str, output_dir: Path, environ: Mapping[str, str]
    ) -> RunSettings:
        contact = _value(environ, CONTACT_VARIABLE)
        settings = cls(postal_code=postal_code, output_dir=output_dir, contact=contact)
        settings.validate()
        return settings


def configuration_hash(
    *,
    store_id: str,
    platform: str,
    postal_code: str,
    http: HttpSettings,
    store_settings: Mapping[str, Any],
    contact_configured: bool,
) -> str:
    """Hash the effective public configuration; never paths or secret values."""
    values = {
        "store": store_id,
        "platform": platform,
        "location": {"postal_code": postal_code},
        "http": asdict(http),
        "store_settings": dict(store_settings),
        "contact_configured": contact_configured,
    }
    try:
        canonical = json.dumps(values, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        raise ValueError("store public settings must be JSON serializable") from None
    return hashlib.sha256(canonical.encode()).hexdigest()


def _value(environ: Mapping[str, str], name: str) -> str | None:
    value = environ.get(name, "").strip()
    return value or None


def _float(environ: Mapping[str, str], name: str, default: float) -> float:
    value = _value(environ, name)
    if value is None:
        return default
    try:
        number = float(value)
    except ValueError:
        raise ValueError(f"{name} must be a number") from None
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _integer(environ: Mapping[str, str], name: str, default: int) -> int:
    value = _value(environ, name)
    if value is None:
        return default
    if not _INTEGER.fullmatch(value):
        raise ValueError(f"{name} must be a decimal integer")
    return int(value)


def _check_range(name: str, value: float, low: float, high: float) -> None:
    if not (math.isfinite(value) and low < value <= high):
        raise ValueError(f"{name} must be in ({low}, {high}]")
