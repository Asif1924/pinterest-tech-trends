#!/usr/bin/env python3
"""Pipeline health monitor + retention enforcer.

Modes (combinable):
  --check       Inspect recent manifests; alert if latest is stale (>26h) or
                if status != success for >=2 consecutive runs.
  --retention   Enforce retention policy: keep N most recent successful and
                M most recent failed runs; tar.gz anything older than D days
                into <root>/archive/ and remove the original run dir.
  --dry-run     Print actions without executing.

If invoked with no mode flags, runs --check then --retention.

Reads config from pinterest_config.json:
  retention.keep_last_successful  (default 30)
  retention.keep_last_failed      (default 10)
  retention.archive_after_days    (default 90)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tarfile
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline_paths as paths
import pipeline_manifest as manifest

CONFIG_PATH = Path(__file__).resolve().parent / "pinterest_config.json"


def _load_cfg() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _load_env() -> dict:
    env = {}
    env_path = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))) / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"')
    return env


def _telegram(text: str, env: dict) -> None:
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_HOME_CHANNEL", "")
    if not (token and chat_id):
        return
    try:
        data = json.dumps({"chat_id": chat_id, "text": text}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def _all_runs() -> list[Path]:
    """Return run dirs sorted oldest -> newest (lexicographic == chronological)."""
    rd = paths.runs_dir()
    if not rd.exists():
        return []
    return sorted([p for p in rd.iterdir() if p.is_dir()])


def _parse_started(m: dict) -> datetime | None:
    s = m.get("started_at")
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def cmd_check(env: dict, alert: bool = True) -> int:
    """Return non-zero exit code on any health issue."""
    runs = _all_runs()
    if not runs:
        msg = "🚨 Pipeline health: no runs found at all"
        print(msg)
        if alert:
            _telegram(msg, env)
        return 1

    latest = manifest.load(runs[-1])
    latest_started = _parse_started(latest)
    issues = []

    if latest_started is not None:
        age = datetime.now(timezone.utc) - latest_started
        if age > timedelta(hours=26):
            issues.append(f"latest run is {age.total_seconds() / 3600:.1f}h old (>26h)")

    # consecutive non-success
    streak = 0
    for rd in reversed(runs[-5:]):
        m = manifest.load(rd)
        if m.get("status") == "success":
            break
        streak += 1
    if streak >= 2:
        issues.append(f"{streak} consecutive non-success runs")

    if issues:
        msg = "🚨 Pipeline health: " + "; ".join(issues)
        print(msg)
        if alert:
            _telegram(msg, env)
        return 2

    print(f"✅ Pipeline health OK (latest: {latest.get('run_id')}, status: {latest.get('status')})")
    return 0


def _archive_run(run_dir: Path, dry_run: bool) -> None:
    paths.archive_dir().mkdir(parents=True, exist_ok=True)
    target = paths.archive_dir() / f"{run_dir.name}.tar.gz"
    print(f"  archive {run_dir.name} -> {target.name}")
    if dry_run:
        return
    with tarfile.open(target, "w:gz") as tar:
        tar.add(run_dir, arcname=run_dir.name)
    shutil.rmtree(run_dir)


def cmd_retention(dry_run: bool = False) -> int:
    cfg = _load_cfg().get("retention", {})
    keep_ok = int(cfg.get("keep_last_successful", 30))
    keep_fail = int(cfg.get("keep_last_failed", 10))
    archive_days = int(cfg.get("archive_after_days", 90))
    threshold = datetime.now(timezone.utc) - timedelta(days=archive_days)

    runs = _all_runs()
    successes, failures, others = [], [], []
    for rd in runs:
        m = manifest.load(rd)
        bucket = successes if m.get("status") == "success" else failures if m.get("status") in ("failed", "partial") else others
        bucket.append((rd, m))

    # Keep the N most recent of each category; evict the rest.
    to_evict = []
    for bucket, keep in [(successes, keep_ok), (failures, keep_fail), (others, 0)]:
        if len(bucket) > keep:
            to_evict.extend(bucket[: len(bucket) - keep])

    # Also force-archive anything started before the day threshold, even if
    # it's inside the keep window. (Long-lived projects: stop ballooning disk.)
    for rd, m in successes + failures + others:
        started = _parse_started(m)
        if started is not None and started < threshold and (rd, m) not in to_evict:
            to_evict.append((rd, m))

    print(f"runs: {len(runs)} (ok={len(successes)}, failed/partial={len(failures)}, other={len(others)})")
    print(f"evicting {len(to_evict)} run(s)")
    for rd, _ in to_evict:
        _archive_run(rd, dry_run)
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true")
    p.add_argument("--retention", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-alert", action="store_true", help="Skip telegram alerts on check failures")
    args = p.parse_args()

    if not (args.check or args.retention):
        args.check = args.retention = True

    env = _load_env()
    rc = 0
    if args.check:
        rc |= cmd_check(env, alert=not args.no_alert)
    if args.retention:
        rc |= cmd_retention(dry_run=args.dry_run)
    sys.exit(rc)


if __name__ == "__main__":
    main()
