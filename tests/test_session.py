from __future__ import annotations

import json
from pathlib import Path

import pytest

from ndevscrap.session import JsonFileSessionProvider, SessionConfigurationError


def test_session_provider_loads_secret_without_transforming_it(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text(
        json.dumps({"headers": {"Authorization": "secret"}, "cookies": {}}),
        encoding="utf-8",
    )

    session = JsonFileSessionProvider(path).load()

    assert session.headers["Authorization"] == "secret"


def test_session_provider_rejects_empty_material(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(SessionConfigurationError, match="headers or cookies"):
        JsonFileSessionProvider(path).load()
