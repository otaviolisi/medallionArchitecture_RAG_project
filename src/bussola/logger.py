"""Logging setup - stdout + rolling file."""

from __future__ import annotations

import logging
import os
from pathlib import Path


def get_logger(name: str = "bussola") -> logging.Logger:
    """Return a configured logger. Idempotent across calls."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logger.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "pipeline.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger
