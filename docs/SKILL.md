---
title: Cron Job Management
tags: [cron, jobs, scheduling, automation]
category: Automation
---

# Cron Job Management Skill

Use this skill when managing, pausing, resuming, or updating Hermes cron jobs.

## Common Operations

| Action | Command |
| --- | --- |
| List jobs | `cronjob action='list'` |
| Update schedule | `cronjob action='update' job_id=<ID> schedule="0 * * * *"` |
| Pause | `cronjob action='pause' job_id=<ID>` |
| Resume | `cronjob action='resume' job_id=<ID>` |
| Run on demand | `cronjob action='run' job_id=<ID>` |
| Remove | `cronjob action='remove' job_id=<ID>` |

Schedules accept standard cron (`min hour dom month dow`) or human shorthand
(`every hour`, `30m`, `every day`).

## Pitfalls

- After every update, verify `last_status == "ok"`.
- Do not pause a job mid-run; wait for it to settle.
- Job IDs are unique — list before creating to avoid duplicates.
- Human-shorthand schedules are stored verbatim; round-trip them with `list`
  to confirm they parse as expected.

## Chained Job Execution Pattern (Pinterest Pipeline)

For pipelines where jobs depend on each other (Job 1 → Job 2 → Job 3) the
Pinterest pipeline uses **subprocess chaining** with a shared run id.

### Implementation

The parent job exec's the child with `HERMES_PIPELINE_RUN_ID` set so all
stages write into the same `~/.hermes/pinterest/runs/<RUN_ID>/` directory:

```python
import os, subprocess, sys
from pathlib import Path

child = Path(__file__).resolve().parent / "pinterest_pin_generator.py"
env = os.environ.copy()
env["HERMES_PIPELINE_RUN_ID"] = run_id      # propagate the run id
subprocess.run(
    [sys.executable, str(child)],
    env=env,
    capture_output=True, text=True,
    timeout=cfg["timeouts"]["job2_subprocess"],
)
```

If the env var is unset (manual re-run), the child resolves the run via the
`~/.hermes/pinterest/current` symlink. Children abort if neither resolves.

### Cron Configuration

| Job | Schedule | `enabled` | Trigger |
| --- | --- | --- | --- |
| Job 1 (`trending_tech_products.py`) | `0 * * * *` | `true` | cron |
| Job 2 (`pinterest_pin_generator.py`) | `30 */6 * * *` | `false` | Job 1 subprocess |
| Job 3 (`pinterest_pin_uploader.py`) | `0 1,7,13,19 * * *` | `false` | Job 2 subprocess |

### Benefits

- Single trigger point — Job 1's schedule drives the whole pipeline.
- Guaranteed ordering, no race against shared symlinks.
- Full chain output captured in Job 1's `hermes cron output`.

### Gotchas

- Per-job timeouts (`pinterest_config.json` → `timeouts.job2_subprocess`,
  etc.) must comfortably exceed worst-case duration.
- Catch `subprocess.TimeoutExpired` / `CalledProcessError` and write the
  failure into the run manifest before raising.
- Never make a downstream job re-trigger an upstream one — closed loop.
