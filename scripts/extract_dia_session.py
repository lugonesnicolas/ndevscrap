"""Create an ignored ClubDIA session file from an authorized browser HAR."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ndevscrap.session import SECRETS_DIRECTORY, validate_session_output
from ndevscrap.stores.dia_session import extract_session_from_har

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / SECRETS_DIRECTORY / "dia-session.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("har", type=Path, help="authorized DIA browser HAR")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    try:
        validate_session_output(args.output, ROOT)
        material = extract_session_from_har(args.har)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        _write_private(args.output, json.dumps(material, separators=(",", ":")))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    print(
        f"Created {args.output} with {len(material['cookies'])} functional cookies; "
        "secret values were not displayed."
    )
    return 0


def _write_private(path: Path, content: str) -> None:
    """Write an owner-only new file, then replace the target atomically.

    The secret is never written into an existing file with wider permissions.
    On Windows the profile ACLs apply.
    """
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
