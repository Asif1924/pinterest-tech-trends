"""Configuration loader for Pinterest CSV upload automation (FR8)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


@dataclass
class Config:
    email: str
    password: str
    csv_path: Path
    manual_wait_seconds: int
    headless: bool
    artifacts_dir: Path


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_config(
    csv_override: Optional[str] = None,
    env_file: Optional[str] = None,
) -> Config:
    """Load configuration from .env / environment variables.

    Raises ValueError if required fields are missing.
    """
    if env_file:
        load_dotenv(env_file, override=False)
    else:
        load_dotenv(override=False)

    email = os.getenv("PINTEREST_EMAIL", "").strip()
    password = os.getenv("PINTEREST_PASSWORD", "")
    csv_raw = csv_override or os.getenv("PINTEREST_CSV_PATH", "").strip()
    manual_wait = int(os.getenv("PINTEREST_MANUAL_WAIT", "120"))
    headless = _env_bool("PINTEREST_HEADLESS", False)
    artifacts = Path(os.getenv("PINTEREST_ARTIFACTS_DIR", "artifacts"))

    missing = []
    if not email:
        missing.append("PINTEREST_EMAIL")
    if not password:
        missing.append("PINTEREST_PASSWORD")
    if not csv_raw:
        missing.append("PINTEREST_CSV_PATH (or --csv flag)")
    if missing:
        raise ValueError(
            "Missing required configuration: " + ", ".join(missing)
        )

    csv_path = Path(csv_raw).expanduser().resolve()
    if not csv_path.is_file():
        raise ValueError(f"CSV file not found: {csv_path}")

    artifacts.mkdir(parents=True, exist_ok=True)

    return Config(
        email=email,
        password=password,
        csv_path=csv_path,
        manual_wait_seconds=manual_wait,
        headless=headless,
        artifacts_dir=artifacts.resolve(),
    )
