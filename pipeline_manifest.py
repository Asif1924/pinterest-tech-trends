"""Per-run manifest read/write helpers.

Schema (manifest.json in each run dir):

    {
      "run_id":     "<iso>",
      "started_at": "<iso utc>",
      "ended_at":   "<iso utc or null>",
      "status":     "started" | "success" | "partial" | "failed",
      "job1":       {"scraped": int, "csv": str, "sources": {...}, "elapsed_s": float},
      "job2":       {"pins_generated": int, "csv": str, "min_pins_gate": int,
                     "excluded_no_media": int, "elapsed_s": float},
      "job3":       {"method": str, "uploaded": int, "failed": int,
                     "pin_urls": [...], "elapsed_s": float},
      "errors":     [ {"stage": str, "message": str, "ts": str}, ... ]
    }

`status` transitions: started -> success (Job 3 ok) | partial (Job 3 partial)
| failed (any stage hard-failed). Writes are atomic (tmp + rename).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from pipeline_paths import MANIFEST_NAME, run_id_of


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def manifest_path(run_dir: Path) -> Path:
    return Path(run_dir) / MANIFEST_NAME


def load(run_dir: Path) -> dict:
    p = manifest_path(run_dir)
    if not p.exists():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save(run_dir: Path, manifest: dict) -> None:
    p = manifest_path(run_dir)
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def init(run_dir: Path) -> dict:
    """Create a fresh manifest with status='started'. Idempotent: returns the
    existing manifest if one is already present (so reruns of Job 1 against
    the same run dir don't clobber accumulated state)."""
    existing = load(run_dir)
    if existing:
        return existing
    m = {
        "run_id": run_id_of(run_dir),
        "started_at": _now_iso(),
        "ended_at": None,
        "status": "started",
        "job1": {},
        "job2": {},
        "job3": {},
        "errors": [],
    }
    save(run_dir, m)
    return m


def update(run_dir: Path, **fields) -> dict:
    """Merge top-level fields into the manifest and save atomically."""
    m = load(run_dir) or init(run_dir)
    for k, v in fields.items():
        m[k] = v
    save(run_dir, m)
    return m


def set_stage(run_dir: Path, stage: str, data: dict) -> dict:
    """Replace the per-stage payload (e.g. set_stage(rd, 'job2', {...}))."""
    m = load(run_dir) or init(run_dir)
    m[stage] = data
    save(run_dir, m)
    return m


def append_error(run_dir: Path, stage: str, message: str) -> dict:
    m = load(run_dir) or init(run_dir)
    m.setdefault("errors", []).append(
        {"stage": stage, "message": message[:500], "ts": _now_iso()}
    )
    save(run_dir, m)
    return m


def finalize(run_dir: Path, status: str) -> dict:
    """Mark run as ended with a terminal status."""
    return update(run_dir, ended_at=_now_iso(), status=status)
