from __future__ import annotations

import io
import json
import logging
import warnings

import pytest

from ndevscrap.observability import configure_logging

SENTINEL = "SENTINEL-secret-value"
LOGGER = logging.getLogger("ndevscrap.tests")


def _lines(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_only_allowlisted_fields_are_serialized() -> None:
    stream = io.StringIO()
    configure_logging(stream=stream)

    LOGGER.info(
        "component_finished",
        extra={
            "event": "component_finished",
            "run_id": "run-1",
            "store": "dia",
            "component": "catalog",
            "status": "success",
            "normalized": 3,
            "headers": {"Cookie": SENTINEL},
            "cookies": {"vtex_session": SENTINEL},
            "token": SENTINEL,
        },
    )

    (line,) = _lines(stream)
    assert set(line) == {
        "ts",
        "level",
        "logger",
        "message",
        "event",
        "run_id",
        "store",
        "component",
        "status",
        "normalized",
    }
    assert line["level"] == "INFO"
    assert SENTINEL not in stream.getvalue()


def test_exceptions_are_reduced_to_their_type() -> None:
    stream = io.StringIO()
    configure_logging(stream=stream)

    try:
        raise ValueError(f"header rejected {SENTINEL}")
    except ValueError:
        LOGGER.exception("component failed")

    (line,) = _lines(stream)
    assert line["exc_type"] == "ValueError"
    assert "Traceback" not in stream.getvalue()
    assert SENTINEL not in stream.getvalue()


def test_configuration_is_idempotent_and_keeps_foreign_handlers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    first, second = io.StringIO(), io.StringIO()
    foreign = logging.StreamHandler(io.StringIO())
    root = logging.getLogger()
    root.addHandler(foreign)
    try:
        configure_logging(stream=first)
        configure_logging(stream=second)

        with caplog.at_level(logging.INFO):
            LOGGER.info("run_started", extra={"event": "run_started"})
    finally:
        root.removeHandler(foreign)

    assert foreign.stream.getvalue() == "run_started\n"
    assert first.getvalue() == ""
    assert len(_lines(second)) == 1
    assert [record.message for record in caplog.records] == ["run_started"]


def test_warnings_are_logged_as_json() -> None:
    stream = io.StringIO()
    configure_logging(stream=stream)

    with warnings.catch_warnings():
        warnings.simplefilter("always")
        warnings.warn("deprecated option", UserWarning, stacklevel=1)

    (line,) = _lines(stream)
    assert line["logger"] == "py.warnings"
    assert line["level"] == "WARNING"
    assert line["message"] == "external log record"


def test_foreign_records_never_interpolate_their_arguments() -> None:
    stream = io.StringIO()
    configure_logging(stream=stream)

    logging.getLogger("urllib3.connection").warning(
        "Failed to parse headers (url=%s): %s",
        "https://shop.example/cupons",
        f"unparsed data: 'Set-Cookie: session={SENTINEL}'",
    )

    (line,) = _lines(stream)
    assert line["logger"] == "urllib3.connection"
    assert line["message"] == "external log record"
    assert SENTINEL not in stream.getvalue()
