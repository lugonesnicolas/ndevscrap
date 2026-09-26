"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections.abc import Sequence
from pathlib import Path

from .config import HttpSettings, RunSettings
from .observability import configure_logging
from .runner import run_store
from .stores import REGISTRY

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ndevscrap")
    subcommands = parser.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run", help="run a store connector")
    run.add_argument("store", choices=sorted(REGISTRY))
    run.add_argument(
        "--postal-code",
        default="1806",
        help="postal code for location-specific prices and availability "
        "(default: 1806)",
    )
    run.add_argument("--output", type=Path, default=Path("output"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)
    if args.command != "run":
        return 1
    try:
        definition = REGISTRY[args.store](os.environ)
        run_settings = RunSettings.from_environment(
            args.postal_code, args.output, os.environ
        )
        http_settings = HttpSettings.from_environment(os.environ)
        manifest, destination = run_store(definition, run_settings, http_settings)
    except ValueError as exc:
        LOGGER.error("configuration error: %s", exc, extra={"event": "run_rejected"})
        return 1
    except OSError as exc:
        LOGGER.error(
            "storage error: %s: %s",
            type(exc).__name__,
            exc,
            extra={"event": "run_failed"},
        )
        return 1
    except Exception as exc:  # noqa: BLE001 - last resort, reported by type only
        LOGGER.error(
            "unexpected error",
            extra={"event": "run_failed", "exc_type": type(exc).__name__},
        )
        return 1
    print(
        json.dumps(
            {
                "status": manifest.status,
                "run_id": manifest.run_id,
                "snapshot": str(destination),
            },
            ensure_ascii=False,
        )
    )
    return {"success": 0, "partial_success": 2}.get(manifest.status, 1)
