"""Centralized path resolution for the Pinterest pipeline.

Layout (single source of truth):

    $HERMES_HOME/pinterest/
    ├── runs/<run_id>/
    │   ├── 01_raw_products.csv      (Job 1 output)
    │   ├── 02_pinterest_bulk.csv    (Job 2 output, Job 3 input)
    │   └── manifest.json
    ├── current -> runs/<run_id>     (symlink, updated atomically by Job 1)
    ├── archive/                     (tar.gz of evicted runs)
    └── logs/

Run identity flows Job 1 -> 2 -> 3 via the HERMES_PIPELINE_RUN_ID env var.
When that var is missing (manual reruns), callers fall back to the `current`
symlink. A new run_id is only minted by `new_run_dir()` (called by Job 1).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# ── Filename constants ──────────────────────────────────────────────────────
RAW_CSV_NAME = "01_raw_products.csv"
BULK_CSV_NAME = "02_pinterest_bulk.csv"
MANIFEST_NAME = "manifest.json"

# ── Env-var contract between pipeline stages ────────────────────────────────
RUN_ID_ENV = "HERMES_PIPELINE_RUN_ID"


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))


def _load_paths_config() -> dict:
    cfg_path = Path(__file__).resolve().parent / "pinterest_config.json"
    try:
        with open(cfg_path) as f:
            return json.load(f).get("paths", {}) or {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def root_dir() -> Path:
    """Resolution order:

    1. ``HERMES_HOME`` env var (if explicitly set in the environment) +
       ``/pinterest`` — lets test harnesses redirect everything.
    2. ``paths.root`` from pinterest_config.json (with ``~`` expansion).
    3. Default: ``~/.hermes/pinterest``.
    """
    if "HERMES_HOME" in os.environ:
        return Path(os.environ["HERMES_HOME"]) / "pinterest"
    override = _load_paths_config().get("root")
    if override:
        return Path(os.path.expanduser(override))
    return _hermes_home() / "pinterest"


def runs_dir() -> Path:
    return root_dir() / "runs"


def archive_dir() -> Path:
    return root_dir() / "archive"


def logs_dir() -> Path:
    return root_dir() / "logs"


def current_link() -> Path:
    return root_dir() / "current"


def _ensure_layout() -> None:
    for d in (runs_dir(), archive_dir(), logs_dir()):
        d.mkdir(parents=True, exist_ok=True)


def new_run_id(now: datetime | None = None) -> str:
    """Filesystem-safe ISO-8601 UTC timestamp, second precision."""
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H-%M-%SZ")


def new_run_dir(run_id: str | None = None) -> Path:
    """Create a fresh per-run directory and return its path. Job 1 only."""
    _ensure_layout()
    run_id = run_id or new_run_id()
    rd = runs_dir() / run_id
    rd.mkdir(parents=True, exist_ok=True)
    return rd


def set_current(run_dir: Path) -> None:
    """Atomically update `current` symlink to point at run_dir."""
    link = current_link()
    tmp = link.with_name(link.name + ".tmp")
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    # Use a relative target so the symlink survives moves of the root dir.
    target = os.path.relpath(run_dir, link.parent)
    os.symlink(target, tmp)
    os.replace(tmp, link)


def current_run_dir() -> Path | None:
    link = current_link()
    if not link.exists():
        return None
    return link.resolve()


def resolve_run_dir(env: os._Environ | dict | None = None) -> Path | None:
    """Look up the current run dir for downstream stages (Job 2 / Job 3).

    Order: HERMES_PIPELINE_RUN_ID env var -> `current` symlink -> None.
    """
    env = env if env is not None else os.environ
    run_id = env.get(RUN_ID_ENV)
    if run_id:
        candidate = runs_dir() / run_id
        if candidate.is_dir():
            return candidate
    return current_run_dir()


def run_id_of(run_dir: Path) -> str:
    return Path(run_dir).name
