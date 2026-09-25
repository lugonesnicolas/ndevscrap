"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from pathlib import Path

from .config import DiaConfig
from .runner import run_dia


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ndevscrap")
    subcommands = parser.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run", help="run a store connector")
    run.add_argument("store", choices=("dia",))
    run.add_argument(
        "--postal-code",
        default="1806",
        help="postal code used for DIA availability and prices (default: 1806)",
    )
    run.add_argument("--output", type=Path, default=Path("output"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = build_parser().parse_args(argv)
    if args.command == "run" and args.store == "dia":
        try:
            config = DiaConfig.from_environment(args.postal_code, args.output)
            manifest, destination = run_dia(config)
        except (OSError, ValueError) as exc:
            logging.getLogger(__name__).error("configuration error: %s", exc)
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
    return 1
