from __future__ import annotations

import json
from pathlib import Path

import pytest

from ndevscrap.session import extract_session_from_har, validate_session_output


def test_extract_session_keeps_only_functional_material(tmp_path: Path) -> None:
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

    material = extract_session_from_har(har)

    assert material["headers"] == {"order-form-id": "order-secret"}
    assert material["cookies"] == {
        "VtexIdclientAutCookie_shop": "auth-secret",
        "vtex_session": "session-secret",
    }
    assert "tracking-value" not in json.dumps(material)
    assert "must-not-be-copied" not in json.dumps(material)


def test_session_output_inside_repository_must_be_ignored() -> None:
    with pytest.raises(ValueError, match="must be under output"):
        validate_session_output(Path("session.json"), Path.cwd())
