"""Secret session providers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .contracts import SessionMaterial


class SessionConfigurationError(RuntimeError):
    """Raised when a local session secret is absent or malformed."""


class JsonFileSessionProvider:
    """Load headers and cookies from an untracked JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> SessionMaterial:
        try:
            data: Any = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SessionConfigurationError(
                "ClubDIA session file is unavailable or invalid"
            ) from exc
        if not isinstance(data, dict):
            raise SessionConfigurationError("ClubDIA session must be a JSON object")
        headers = _string_mapping(data.get("headers", {}), "headers")
        cookies = _string_mapping(data.get("cookies", {}), "cookies")
        if not headers and not cookies:
            raise SessionConfigurationError(
                "ClubDIA session must contain headers or cookies"
            )
        return SessionMaterial(headers=headers, cookies=cookies)


def extract_session_from_har(har_path: Path) -> dict[str, dict[str, str]]:
    """Extract only the minimum ClubDIA session material from a browser HAR."""
    payload: Any = json.loads(har_path.read_text(encoding="utf-8"))
    entries = payload.get("log", {}).get("entries", [])
    if not isinstance(entries, list):
        raise TypeError("HAR does not contain a valid log.entries list")

    cookies: dict[str, str] = {}
    order_form_id: str | None = None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        request = entry.get("request", {})
        response = entry.get("response", {})
        if not isinstance(request, dict) or not isinstance(response, dict):
            continue
        path = urlparse(str(request.get("url", ""))).path
        if path == _TOKEN_PATH and response.get("status") == 200:
            cookies = _functional_cookies(request.get("cookies", []))
        if path.startswith(_ORDER_FORM_PREFIX) and response.get("status") == 200:
            candidate = _order_form_id(response)
            if candidate:
                order_form_id = candidate

    if not any(name.startswith("VtexIdclientAutCookie_") for name in cookies):
        raise ValueError("HAR does not contain a successful authenticated ClubDIA call")
    if not order_form_id:
        raise ValueError("HAR does not contain an order-form-id required by ClubDIA")
    return {
        "headers": {"order-form-id": order_form_id},
        "cookies": cookies,
    }


def validate_session_output(path: Path, repository_root: Path) -> None:
    """Refuse a session file in a versionable repository location."""
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(repository_root.resolve())
    except ValueError:
        return
    if not relative.parts or relative.parts[0] != "output":
        raise ValueError("session files inside the repository must be under output/")


def _string_mapping(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise SessionConfigurationError(f"ClubDIA {field} must contain strings")
    return dict(value)


_TOKEN_PATH = "/_v/private/club-dia/_v1/token-by-user"
_ORDER_FORM_PREFIX = "/api/checkout/pub/orderForm"
_COOKIE_NAMES = frozenset(
    {"CheckoutLocale", "validatedLogin", "vtex_segment", "vtex_session"}
)


def _functional_cookies(value: Any) -> dict[str, str]:
    if not isinstance(value, list):
        return {}
    return {
        item["name"]: item["value"]
        for item in value
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and isinstance(item.get("value"), str)
        and (
            item["name"].startswith("VtexIdclientAutCookie_")
            or item["name"] in _COOKIE_NAMES
        )
    }


def _order_form_id(response: dict[str, Any]) -> str | None:
    content = response.get("content", {})
    if not isinstance(content, dict) or not isinstance(content.get("text"), str):
        return None
    try:
        payload = json.loads(content["text"])
    except json.JSONDecodeError:
        return None
    value = payload.get("orderFormId") if isinstance(payload, dict) else None
    return value if isinstance(value, str) and value else None
