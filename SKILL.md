# ---
# Title: Cron Job Management
# Tags: cron, jobs, scheduling, automation
# Created: 2026-04-15
# Last Updated: 2026-04-15
# Category: Automation
# ---

# Cron Job Management Skill

Use this skill when managing, pausing, resuming, or updating scheduled cron jobs in the Hermes agent.

## Overview

This skill provides a complete guide for managing cron jobs including listing, updating schedules, pausing/resuming, and running jobs on demand.

## Common Operations

### 1. List Jobs
- Use `cronjob action='list'` to get all current job configurations
- Review job ID, status, schedule, last run time, etc.

### 2. Update Schedule
- Use `cronjob action='update'` with new schedule parameter:
- Valid schedules use cron syntax: `* * * * *`, `0 */6 * * *`, `every hour`, `30m`, or custom expressions
- Example: To run every hour, set `schedule="* * * * *"`

### 3. Pause/Resume Jobs
- Use action='pause' to pause a job (saves state)
- Use action='resume' to resume it after unpausing
- Check `paused_at` and `paused_reason` fields to see why paused

### 4. Run On-Demand
- Use action='run' with job_id to execute immediately without waiting for schedule

### 5. Remove Jobs
- First list jobs to find job_id, then use action='remove'

## Pitfalls & Tips

- **Schedule Syntax**: Cron expressions follow standard format (minute hour day month weekday) or human-friendly formats like "every hour", "30m", "every day"
- **Race Conditions**: When pausing a job that's running, wait for it to complete before pausing
- **State Changes**: Always check `last_status` after updates - should be 'ok'
- **Job ID Uniqueness**: Each job must have unique ID; use cronjob list first to avoid duplicates

## Example Workflow

```bash
# List jobs to find the one you want to modify
cronjob action='list'

# Update a specific job's schedule (example: every hour)
cronjob action='update' job_id="YOUR_JOB_ID" schedule="* * * * *"

# Verify changes
cronjob action='list' --jobs YOUR_JOB_ID
```

## When to Use This Skill

- Setting up new automated jobs
- Adjusting schedules during development/testing
- Managing production pipelines (e.g., Pinterest automation)
- Debugging timing issues by reviewing last_run_at timestamps
- Pausing/resuming jobs for maintenance or troubleshooting

---

## Chained Job Execution Pattern

For pipelines where jobs depend on each other (Job 1 → Job 2 → Job 3), use **subprocess chaining**:

### Implementation

**Job 1** triggers **Job 2** at the end of its `main()` function:
```python
import subprocess
import os

pin_gen_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pinterest_pin_generator.py")
result = subprocess.run(
    [sys.executable, pin_gen_script],
    capture_output=True, text=True, timeout=300,
)
```

**Job 2** triggers **Job 3** the same way at the end of its execution.

### Cron Configuration

- **Job 1**: Keep on schedule (e.g., every hour) — `enabled: true`
- **Job 2**: Pause independent scheduling — `enabled: false` (triggered by Job 1)
- **Job 3**: Pause independent scheduling — `enabled: false` (triggered by Job 2)

### Benefits

- No race conditions between jobs
- Guaranteed execution order
- Single trigger point (Job 1 schedule controls the whole pipeline)
- Easier debugging (full chain output in Job 1's logs)

### Pitfalls

- **Timeout handling**: Set appropriate timeouts for each chained job (e.g., 300 seconds)
- **Error propagation**: Each job should catch exceptions from subprocess and report failures
- **No circular dependencies**: Ensure Job 3 doesn't trigger Job 1
- **Logging**: Chain output is captured in parent job's stdout — review full logs for debugging
