"""Secret session providers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import AuthenticationRequiredError, SessionMaterial

SECRETS_DIRECTORY = ".secrets"


class SessionConfigurationError(AuthenticationRequiredError):
    """Raised when a local session secret is absent or malformed."""


class JsonFileSessionProvider:
    """Load headers and cookies from an untracked JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> SessionMaterial:
        try:
            data: Any = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = None
        if data is None:
            # Raised outside the except block: a decoding error can quote the
            # secret file content.
            raise SessionConfigurationError("session file is unavailable or invalid")
        if not isinstance(data, dict):
            raise SessionConfigurationError("session must be a JSON object")
        headers = _string_mapping(data.get("headers", {}), "headers")
        cookies = _string_mapping(data.get("cookies", {}), "cookies")
        if not headers and not cookies:
            raise SessionConfigurationError("session must contain headers or cookies")
        return SessionMaterial(headers=headers, cookies=cookies)


def validate_session_output(path: Path, repository_root: Path) -> None:
    """Refuse a session file in a versionable repository location."""
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(repository_root.resolve())
    except ValueError:
        return
    if len(relative.parts) < 2 or relative.parts[0] != SECRETS_DIRECTORY:
        raise ValueError(
            f"session files inside the repository must be under {SECRETS_DIRECTORY}/"
        )


def _string_mapping(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise SessionConfigurationError(f"session {field} must contain strings")
    return dict(value)
