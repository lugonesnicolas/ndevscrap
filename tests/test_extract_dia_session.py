from __future__ import annotations

import importlib.util
import json
import stat
import sys
from pathlib import Path

import pytest

from ndevscrap.session import validate_session_output
from ndevscrap.stores.dia_session import extract_session_from_har

REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY / "scripts" / "extract_dia_session.py"


def _har(tmp_path: Path) -> Path:
    har = tmp_path / "session.har"
    har.write_text(
        json.dumps(
            {
                "log": {
                    "entries": [
                        {
                            "request": {
                                "url": (
                                    "https://shop.example/_v/private/club-dia/"
                                    "_v1/token-by-user"
                                ),
                                "cookies": [
                                    {
                                        "name": "VtexIdclientAutCookie_shop",
                                        "value": "auth-secret",
                                    },
                                    {"name": "vtex_session", "value": "session-secret"},
                                    {"name": "_ga", "value": "tracking-value"},
                                ],
                            },
                            "response": {"status": 200},
                        },
                        {
                            "request": {
                                "url": "https://shop.example/api/checkout/pub/orderForm"
                            },
                            "response": {
                                "status": 200,
                                "content": {
                                    "text": json.dumps(
                                        {
                                            "orderFormId": "order-secret",
                                            "clientProfileData": {
                                                "email": "must-not-be-copied@example.invalid"
                                            },
                                        }
                                    )
                                },
                            },
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    return har


def test_extract_session_keeps_only_functional_material(tmp_path: Path) -> None:
    material = extract_session_from_har(_har(tmp_path))

    assert material["headers"] == {"order-form-id": "order-secret"}
    assert material["cookies"] == {
        "VtexIdclientAutCookie_shop": "auth-secret",
        "vtex_session": "session-secret",
    }
    assert "tracking-value" not in json.dumps(material)
    assert "must-not-be-copied" not in json.dumps(material)


def test_session_output_inside_repository_must_be_under_secrets() -> None:
    with pytest.raises(ValueError, match=r"must be under \.secrets"):
        validate_session_output(Path("session.json"), Path.cwd())
    with pytest.raises(ValueError, match=r"must be under \.secrets"):
        validate_session_output(
            REPOSITORY / "output" / "secrets" / "dia-session.json", REPOSITORY
        )

    with pytest.raises(ValueError, match=r"must be under \.secrets"):
        validate_session_output(REPOSITORY / ".secrets", REPOSITORY)

    validate_session_output(REPOSITORY / ".secrets" / "dia-session.json", REPOSITORY)


def test_session_output_outside_the_repository_is_accepted(tmp_path: Path) -> None:
    validate_session_output(tmp_path / "dia-session.json", tmp_path / "repository")


def _script():
    spec = importlib.util.spec_from_file_location("extract_dia_session", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_defaults_to_the_secrets_directory() -> None:
    assert _script().DEFAULT_OUTPUT == REPOSITORY / ".secrets" / "dia-session.json"


def test_script_writes_the_session_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "nested" / "dia-session.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["extract_dia_session.py", str(_har(tmp_path)), "--output", str(output)],
    )

    assert _script().main() == 0

    assert json.loads(output.read_text(encoding="utf-8"))["headers"] == {
        "order-form-id": "order-secret"
    }
    if sys.platform != "win32":
        assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_har_with_an_unexpected_shape_is_rejected(tmp_path: Path) -> None:
    har = tmp_path / "list.har"
    har.write_text("[]", encoding="utf-8")

    with pytest.raises(TypeError, match="log.entries"):
        extract_session_from_har(har)


def test_script_replaces_an_existing_file_without_widening_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "dia-session.json"
    output.write_text("old", encoding="utf-8")
    if sys.platform != "win32":
        output.chmod(0o644)
    monkeypatch.setattr(
        sys,
        "argv",
        ["extract_dia_session.py", str(_har(tmp_path)), "--output", str(output)],
    )

    assert _script().main() == 0

    assert json.loads(output.read_text(encoding="utf-8"))["cookies"]
    assert [path.name for path in tmp_path.iterdir() if path.suffix == ".tmp"] == []
    if sys.platform != "win32":
        assert stat.S_IMODE(output.stat().st_mode) == 0o600
