from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ndevscrap.config import DiaConfig
from ndevscrap.contracts import RunContext
from ndevscrap.runner import _run_clubdia
from ndevscrap.transport import HttpStatusError


class ExpiredSessionTransport:
    retries = 0

    def request(self, request):
        raise HttpStatusError(401, request.url)


def test_expired_clubdia_session_is_component_failure(tmp_path: Path) -> None:
    session = tmp_path / "session.json"
    session.write_text(json.dumps({"cookies": {"session": "secret"}}))
    config = DiaConfig(
        postal_code="1000",
        output_dir=tmp_path,
        session_file=session,
        base_url="https://shop.example",
    )
    context = RunContext("run", "dia", "1000", datetime(2026, 9, 23, tzinfo=UTC))

    coupons, result = _run_clubdia(config, context, ExpiredSessionTransport())

    assert coupons is None
    assert result.status == "authentication_required"
    assert "secret" not in repr(result.to_dict())


def test_missing_clubdia_session_is_actionable(tmp_path: Path) -> None:
    config = DiaConfig(postal_code="1806", output_dir=tmp_path)
    context = RunContext("run", "dia", "1806", datetime(2026, 9, 25, tzinfo=UTC))

    coupons, result = _run_clubdia(config, context, ExpiredSessionTransport())

    assert coupons is None
    assert result.status == "authentication_required"
    assert "NDEVSCRAP_DIA_SESSION_FILE" in result.errors[0]
