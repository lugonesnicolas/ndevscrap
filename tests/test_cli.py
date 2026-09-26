from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ndevscrap import cli
from ndevscrap.models import ComponentResult, RunManifest


def _manifest(status: str) -> RunManifest:
    moment = datetime(2026, 9, 26, tzinfo=UTC)
    return RunManifest(
        run_id="run-1",
        snapshot_id="dia:1806:2026-09-26",
        connector_version="1.0.0",
        store="dia",
        postal_code="1806",
        started_at=moment,
        finished_at=moment,
        configuration_hash="hash",
        status=status,
        components={"catalog": ComponentResult(status="success")},
        duration_seconds=1.0,
    )


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
    monkeypatch.setattr(cli, "run_dia", lambda config: (_manifest(status), destination))

    result = cli.main(["run", "dia", "--output", str(tmp_path)])

    assert result == exit_code
    line = json.loads(capsys.readouterr().out)
    assert line == {"status": status, "run_id": "run-1", "snapshot": str(destination)}


def test_invalid_configuration_returns_one(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    def invalid(config):
        raise ValueError("page_size must be between 1 and 50")

    monkeypatch.setattr(cli, "run_dia", invalid)

    with caplog.at_level(logging.ERROR):
        result = cli.main(["run", "dia", "--output", str(tmp_path)])

    assert result == 1
    assert "configuration error" in caplog.text


def test_storage_failure_is_not_reported_as_configuration(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    def locked(config):
        raise PermissionError("current directory is locked")

    monkeypatch.setattr(cli, "run_dia", locked)

    with caplog.at_level(logging.ERROR):
        result = cli.main(["run", "dia", "--output", str(tmp_path)])

    assert result == 1
    assert "storage error" in caplog.text
    assert "configuration error" not in caplog.text
