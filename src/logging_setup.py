"""Basic logging configuration for emperor."""

from __future__ import annotations

import logging
import os
import sys


def setup_logging(level: str | None = None) -> None:
    """Configure root logger once with a concise format."""
    log_level = (level or os.environ.get("EMPEROR_LOG_LEVEL", "WARNING")).upper()
    numeric = getattr(logging, log_level, logging.WARNING)

    root = logging.getLogger()
    if root.handlers:
        root.setLevel(numeric)
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(numeric)
