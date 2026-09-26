"""Structured JSON logging that never serializes request material."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, TextIO

ALLOWED_FIELDS = (
    "event",
    "run_id",
    "store",
    "component",
    "status",
    "discovered",
    "normalized",
    "rejected",
    "duplicates",
    "retries",
    "requests",
    "duration_seconds",
    "exc_type",
)
_MARKER = "_ndevscrap_json"
_OWN_LOGGER = "ndevscrap"


class JsonLogFormatter(logging.Formatter):
    """Render one JSON object per record from an allowlist of fields.

    Tracebacks, ``exc_info`` and any ``extra`` outside the allowlist are
    dropped; an exception is reduced to its type name. Records from other
    libraries (urllib3, warnings) may interpolate raw headers, so only their
    logger and level are kept, with a fixed message.
    """

    def format(self, record: logging.LogRecord) -> str:
        own = record.name == _OWN_LOGGER or record.name.startswith(f"{_OWN_LOGGER}.")
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage() if own else "external log record",
        }
        for name in ALLOWED_FIELDS:
            value = record.__dict__.get(name)
            if value is not None:
                payload[name] = value
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(stream: TextIO | None = None, level: int = logging.INFO) -> None:
    """Install the JSON handler on the root logger, replacing only its own."""
    remove_json_logging()
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonLogFormatter())
    setattr(handler, _MARKER, True)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(level)
    logging.captureWarnings(True)


def remove_json_logging() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _MARKER, False):
            root.removeHandler(handler)
            handler.close()
    logging.captureWarnings(False)
