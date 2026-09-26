from __future__ import annotations

from pathlib import Path

import pytest

from ndevscrap.config import HttpSettings, RunSettings, configuration_hash

TIMEOUT = "NDEVSCRAP_HTTP_TIMEOUT_SECONDS"
RATE = "NDEVSCRAP_HTTP_REQUESTS_PER_SECOND"
RETRIES = "NDEVSCRAP_HTTP_MAX_RETRIES"
RETRY_AFTER = "NDEVSCRAP_HTTP_MAX_RETRY_AFTER_SECONDS"


def test_http_settings_defaults() -> None:
    settings = HttpSettings.from_environment({})

    assert settings == HttpSettings(
        timeout_seconds=20.0,
        requests_per_second=1.0,
        max_retries=3,
        max_retry_after_seconds=120.0,
    )


def test_http_settings_read_the_environment() -> None:
    settings = HttpSettings.from_environment(
        {TIMEOUT: "30", RATE: "0.5", RETRIES: "5", RETRY_AFTER: "60"}
    )

    assert settings == HttpSettings(30.0, 0.5, 5, 60.0)


def test_empty_http_variables_use_defaults() -> None:
    settings = HttpSettings.from_environment(
        {TIMEOUT: "", RATE: " ", RETRIES: "", RETRY_AFTER: ""}
    )

    assert settings == HttpSettings()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        (TIMEOUT, "abc"),
        (TIMEOUT, "0"),
        (TIMEOUT, "-1"),
        (TIMEOUT, "300.5"),
        (TIMEOUT, "nan"),
        (TIMEOUT, "inf"),
        (RATE, "0"),
        (RATE, "2.5"),
        (RATE, "nan"),
        (RETRIES, "3.0"),
        (RETRIES, "1e1"),
        (RETRIES, "-1"),
        (RETRIES, "11"),
        (RETRIES, "x"),
        (RETRIES, "\u0663"),
        (RETRIES, "+3"),
        (RETRY_AFTER, "0"),
        (RETRY_AFTER, "3600.5"),
        (RETRY_AFTER, "inf"),
    ],
)
def test_invalid_http_variables_are_configuration_errors(name: str, value: str) -> None:
    with pytest.raises(ValueError, match=name):
        HttpSettings.from_environment({name: value})


def test_invalid_http_value_is_not_echoed() -> None:
    with pytest.raises(ValueError) as error:
        HttpSettings.from_environment({TIMEOUT: "SENTINEL-value"})

    assert "SENTINEL" not in str(error.value)


@pytest.mark.parametrize(
    "settings",
    [
        HttpSettings(timeout_seconds=0),
        HttpSettings(requests_per_second=3),
        HttpSettings(max_retries=11),
        HttpSettings(max_retry_after_seconds=4000),
    ],
)
def test_http_settings_validate_ranges(settings: HttpSettings) -> None:
    with pytest.raises(ValueError):
        settings.validate()


def test_run_settings_read_contact(tmp_path: Path) -> None:
    settings = RunSettings.from_environment(
        "1806", tmp_path, {"NDEVSCRAP_CONTACT": "ops@example.com"}
    )

    assert settings == RunSettings("1806", tmp_path, "ops@example.com")
    assert (
        RunSettings.from_environment(
            "1806", tmp_path, {"NDEVSCRAP_CONTACT": ""}
        ).contact
        is None
    )


@pytest.mark.parametrize(
    "contact", ["ops@example.com\r\nX-Injected: 1", "operación@example.com", "x" * 201]
)
def test_invalid_contact_is_a_configuration_error(tmp_path: Path, contact: str) -> None:
    with pytest.raises(ValueError, match="NDEVSCRAP_CONTACT"):
        RunSettings("1806", tmp_path, contact).validate()


def test_blank_postal_code_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="postal_code"):
        RunSettings(" ", tmp_path).validate()


def _hash(**overrides: object) -> str:
    values: dict[str, object] = {
        "store_id": "dia",
        "platform": "vtex",
        "postal_code": "1806",
        "http": HttpSettings(),
        "store_settings": {"base_url": "https://shop.example"},
        "contact_configured": False,
    }
    values.update(overrides)
    return configuration_hash(**values)  # type: ignore[arg-type]


def test_configuration_hash_covers_public_settings() -> None:
    assert _hash() == _hash()
    assert _hash() != _hash(http=HttpSettings(requests_per_second=2))
    assert _hash() != _hash(postal_code="1000")
    assert _hash() != _hash(store_settings={"base_url": "https://other.example"})
    assert _hash() != _hash(contact_configured=True)
