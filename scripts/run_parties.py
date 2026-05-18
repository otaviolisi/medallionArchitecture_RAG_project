"""Run the parties bronze extraction.

Usage:
    python scripts/run_parties.py                  # full snapshot
    python scripts/run_parties.py --limit 3        # smoke test (3 parties)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

# allow running directly without installing: add src/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bussola.bronze.parties import extract  # noqa: E402


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Bussola Publica - parties bronze extraction"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap parties count (smoke testing). Default: all.",
    )
    args = parser.parse_args()

    extract(limit=args.limit)


if __name__ == "__main__":
    main()