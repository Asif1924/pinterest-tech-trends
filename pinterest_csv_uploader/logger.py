"""Structured logging setup (FR6)."""
from __future__ import annotations

import logging
from pathlib import Path


def setup_logger(artifacts_dir: Path, name: str = "pinterest_csv") -> logging.Logger:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    log_file = artifacts_dir / "run.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger
