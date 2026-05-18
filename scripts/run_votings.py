"""Run the votings bronze extraction.

Usage:
    python scripts/run_votings.py                 # default: 3-month window
    python scripts/run_votings.py --months 1      # smaller window for testing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bussola.bronze.votings import DEFAULT_WINDOW_MONTHS, extract  # noqa: E402


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Bussola Publica - votings bronze extraction"
    )
    parser.add_argument(
        "--months",
        type=int,
        default=DEFAULT_WINDOW_MONTHS,
        help=f"Search window width in months ending today (default: {DEFAULT_WINDOW_MONTHS}).",
    )
    args = parser.parse_args()

    extract(months=args.months)


if __name__ == "__main__":
    main()