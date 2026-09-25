"""Create an ignored ClubDIA session file from an authorized browser HAR."""

from __future__ import annotations

import argparse
import json
import stat
from pathlib import Path

from ndevscrap.session import extract_session_from_har, validate_session_output

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "output" / "secrets" / "dia-session.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("har", type=Path, help="authorized DIA browser HAR")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    try:
        validate_session_output(args.output, ROOT)
        material = extract_session_from_har(args.har)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(material, separators=(",", ":")), encoding="utf-8"
        )
        args.output.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    print(
        f"Created {args.output} with {len(material['cookies'])} functional cookies; "
        "secret values were not displayed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
