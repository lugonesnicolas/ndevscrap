from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ndevscrap import cli
from ndevscrap.config import HttpSettings, RunSettings
from ndevscrap.models import ComponentResult, RunManifest

SENTINEL = "SENTINEL-secret-value"


def _manifest(status: str) -> RunManifest:
    moment = datetime(2026, 9, 26, tzinfo=UTC)
    return RunManifest(
        run_id="run-1",
        snapshot_id="dia:1806:2026-09-26",
        platform="vtex",
        store="dia",
        location={"postal_code": "1806"},
        package_version="0.1.0",
        configuration_hash="hash",
        status=status,
        started_at=moment,
        finished_at=moment,
        duration_seconds=1.0,
        components={"catalog": ComponentResult(status="success")},
    )


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "NDEVSCRAP_DIA_SESSION_FILE",
        "NDEVSCRAP_DIA_BASE_URL",
        "NDEVSCRAP_CONTACT",
        "NDEVSCRAP_HTTP_TIMEOUT_SECONDS",
        "NDEVSCRAP_HTTP_REQUESTS_PER_SECOND",
        "NDEVSCRAP_HTTP_MAX_RETRIES",
        "NDEVSCRAP_HTTP_MAX_RETRY_AFTER_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    ("status", "exit_code"),
    [("success", 0), ("partial_success", 2), ("failed", 1)],
)
def test_run_exit_code_follows_manifest_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    status: str,
    exit_code: int,
) -> None:
    destination = tmp_path / "attempts" / "2026-09-26" / "run-1"
    calls = []

    def fake_run(definition, run_settings, http_settings):
        calls.append((definition, run_settings, http_settings))
        return _manifest(status), destination

    monkeypatch.setattr(cli, "run_store", fake_run)

    result = cli.main(["run", "dia", "--output", str(tmp_path)])

    assert result == exit_code
    line = json.loads(capsys.readouterr().out)
    assert line == {"status": status, "run_id": "run-1", "snapshot": str(destination)}
    definition, run_settings, _ = calls[0]
    assert definition.store_id == "dia"
    assert run_settings.postal_code == "1806"
    assert run_settings.output_dir == tmp_path


def test_invalid_configuration_returns_one(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    def invalid(definition, run_settings, http_settings):
        raise ValueError("page_size must be between 1 and 50")

    monkeypatch.setattr(cli, "run_store", invalid)

    with caplog.at_level(logging.ERROR):
        result = cli.main(["run", "dia", "--output", str(tmp_path)])

    assert result == 1
    assert "configuration error" in caplog.text


def test_storage_failure_is_not_reported_as_configuration(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    def locked(definition, run_settings, http_settings):
        raise PermissionError("current directory is locked")

    monkeypatch.setattr(cli, "run_store", locked)

    with caplog.at_level(logging.ERROR):
        result = cli.main(["run", "dia", "--output", str(tmp_path)])

    assert result == 1
    assert "storage error" in caplog.text
    assert "configuration error" not in caplog.text


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("NDEVSCRAP_HTTP_REQUESTS_PER_SECOND", "5"),
        ("NDEVSCRAP_HTTP_MAX_RETRIES", "SENTINEL"),
        ("NDEVSCRAP_CONTACT", f"ops\r\n{SENTINEL}"),
        ("NDEVSCRAP_DIA_BASE_URL", f"https://user:{SENTINEL}@shop.example"),
    ],
)
def test_invalid_environment_is_a_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    name: str,
    value: str,
) -> None:
    def unexpected(*args):
        raise AssertionError("run_store must not be called")

    monkeypatch.setattr(cli, "run_store", unexpected)
    monkeypatch.setenv(name, value)
    output = tmp_path / "out"

    with caplog.at_level(logging.ERROR):
        result = cli.main(["run", "dia", "--output", str(output)])

    assert result == 1
    assert "configuration error" in caplog.text
    assert SENTINEL not in caplog.text
    assert SENTINEL not in capsys.readouterr().err
    assert not output.exists()


def test_unexpected_failure_is_logged_by_type_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    def broken(definition, run_settings, http_settings):
        raise KeyError(SENTINEL)

    monkeypatch.setattr(cli, "run_store", broken)

    result = cli.main(["run", "dia", "--output", str(tmp_path)])

    assert result == 1
    stderr = capsys.readouterr().err
    lines = [json.loads(line) for line in stderr.splitlines()]
    assert any(line.get("exc_type") == "KeyError" for line in lines)
    assert SENTINEL not in stderr
    assert "Traceback" not in stderr


def test_unknown_store_is_rejected_by_the_parser(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(["run", "other", "--output", str(tmp_path)])

    assert error.value.code == 2


def test_valid_environment_reaches_the_runner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = []

    def fake_run(definition, run_settings, http_settings):
        calls.append((run_settings, http_settings))
        return _manifest("success"), tmp_path

    monkeypatch.setattr(cli, "run_store", fake_run)
    monkeypatch.setenv("NDEVSCRAP_HTTP_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("NDEVSCRAP_HTTP_REQUESTS_PER_SECOND", "0.5")
    monkeypatch.setenv("NDEVSCRAP_HTTP_MAX_RETRIES", "5")
    monkeypatch.setenv("NDEVSCRAP_HTTP_MAX_RETRY_AFTER_SECONDS", "60")
    monkeypatch.setenv("NDEVSCRAP_CONTACT", "ops@example.com")

    assert (
        cli.main(["run", "dia", "--postal-code", "1000", "--output", str(tmp_path)])
        == 0
    )

    run_settings, http_settings = calls[0]
    assert http_settings == HttpSettings(30, 0.5, 5, 60)
    assert run_settings == RunSettings("1000", tmp_path, "ops@example.com")
