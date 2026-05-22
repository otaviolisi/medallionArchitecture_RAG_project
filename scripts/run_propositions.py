"""Run the propositions bronze extraction.

Usage:
    python scripts/run_propositions.py                   # full 12-month backfill
    python scripts/run_propositions.py --months 3        # 3-month window
    python scripts/run_propositions.py --limit 5         # smoke test (5 fan-out calls)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bussola.bronze.propositions import DEFAULT_WINDOW_MONTHS, extract  # noqa: E402


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Bussola Publica - propositions bronze extraction"
    )
    parser.add_argument(
        "--months",
        type=int,
        default=DEFAULT_WINDOW_MONTHS,
        help=f"Initial backfill window in months (default: {DEFAULT_WINDOW_MONTHS}).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap fan-out calls for smoke testing. Default: all.",
    )
    args = parser.parse_args()

    extract(months=args.months, limit=args.limit)


if __name__ == "__main__":
    main()
