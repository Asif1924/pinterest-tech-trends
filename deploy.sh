#!/usr/bin/env bash
set -euo pipefail

# Pinterest Tech Trends - Deploy Script
# Syncs the scraper script, venv, and cron job config to Hermes Agent
#
# Usage:
#   ./deploy.sh           # Deploy script + update cron job + sync venv
#   ./deploy.sh --dry-run # Show what would change without applying

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_SCRIPTS="$HERMES_HOME/scripts"
CRON_JOBS="$HERMES_HOME/cron/jobs.json"
VENV_DIR="$HERMES_SCRIPTS/.venv"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "=== DRY RUN MODE ==="
fi

echo "Pinterest Tech Trends - Deploy"
echo "==============================="
echo "Source:     $SCRIPT_DIR"
echo "Hermes:     $HERMES_HOME"
echo "Venv:       $VENV_DIR"
echo ""

# --- Check prerequisites ---
if [[ ! -d "$HERMES_HOME" ]]; then
    echo "ERROR: Hermes home not found at $HERMES_HOME"
    echo "Install Hermes Agent first: https://github.com/NousResearch/hermes-agent"
    exit 1
fi

if [[ ! -f "$SCRIPT_DIR/trending_tech_products.py" ]]; then
    echo "ERROR: trending_tech_products.py not found in $SCRIPT_DIR"
    exit 1
fi

if [[ ! -f "$SCRIPT_DIR/pinterest_pin_generator.py" ]]; then
    echo "WARNING: pinterest_pin_generator.py not found in $SCRIPT_DIR"
fi

# --- Step 1: Deploy the scraper script ---
echo "1. Deploying scraper script..."
mkdir -p "$HERMES_SCRIPTS"

if [[ "$DRY_RUN" == true ]]; then
    for F in trending_tech_products.py pinterest_pin_generator.py pinterest_pin_uploader.py \
             trending_tech_products.sh pinterest_pin_generator.sh pinterest_pin_uploader.sh \
             pipeline_paths.py pipeline_manifest.py pinterest_pipeline_health.py \
             pinterest_config.json .env; do
        if [[ ! -f "$SCRIPT_DIR/$F" ]]; then
            continue
        fi
        if diff -q "$SCRIPT_DIR/$F" "$HERMES_SCRIPTS/$F" &>/dev/null; then
            echo "   [no changes] $F"
        else
            echo "   [would update] $F"
        fi
    done
else
    cp "$SCRIPT_DIR/trending_tech_products.py" "$HERMES_SCRIPTS/trending_tech_products.py"
    echo "   ✓ Copied to $HERMES_SCRIPTS/trending_tech_products.py"
    # pinterest_config.json is the single source of truth. (config.json in the repo
    # root is a stale snapshot; the Python code never reads it.)
    if [[ -f "$SCRIPT_DIR/pinterest_config.json" ]]; then
        cp "$SCRIPT_DIR/pinterest_config.json" "$HERMES_SCRIPTS/pinterest_config.json"
        echo "   ✓ Copied config to $HERMES_SCRIPTS/pinterest_config.json"
    fi
    if [[ -f "$SCRIPT_DIR/pinterest_pin_generator.py" ]]; then
        cp "$SCRIPT_DIR/pinterest_pin_generator.py" "$HERMES_SCRIPTS/pinterest_pin_generator.py"
        echo "   ✓ Copied to $HERMES_SCRIPTS/pinterest_pin_generator.py"
    fi
    if [[ -f "$SCRIPT_DIR/pinterest_pin_uploader.py" ]]; then
        cp "$SCRIPT_DIR/pinterest_pin_uploader.py" "$HERMES_SCRIPTS/pinterest_pin_uploader.py"
        echo "   ✓ Copied to $HERMES_SCRIPTS/pinterest_pin_uploader.py"
    fi
    # Shared modules — must be alongside the job scripts so Python imports resolve.
    for MOD in pipeline_paths.py pipeline_manifest.py pinterest_pipeline_health.py; do
        if [[ -f "$SCRIPT_DIR/$MOD" ]]; then
            cp "$SCRIPT_DIR/$MOD" "$HERMES_SCRIPTS/$MOD"
            echo "   ✓ Copied to $HERMES_SCRIPTS/$MOD"
        fi
    done
    # Bash shims — these are what cron actually invokes (see cron_job*.json). They
    # exec the project venv's python3 so scrapling/playwright/etc. are importable.
    # Without them, Hermes runs the .py files under its own interpreter (which does
    # not ship those packages) and Amazon scraping silently no-ops.
    for SH in trending_tech_products.sh pinterest_pin_generator.sh pinterest_pin_uploader.sh; do
        if [[ -f "$SCRIPT_DIR/$SH" ]]; then
            cp "$SCRIPT_DIR/$SH" "$HERMES_SCRIPTS/$SH"
            chmod +x "$HERMES_SCRIPTS/$SH"
            echo "   ✓ Copied to $HERMES_SCRIPTS/$SH"
        fi
    done
    if [[ -f "$SCRIPT_DIR/.env" ]]; then
        cp "$SCRIPT_DIR/.env" "$HERMES_SCRIPTS/.env"
        chmod 600 "$HERMES_SCRIPTS/.env"
        echo "   ✓ Copied .env (secrets) to $HERMES_SCRIPTS/.env"
    fi
fi

# --- Step 2: Create / update the venv ---
echo ""
echo "2. Managing Python virtual environment..."

# Check if requirements.txt has actual packages (non-empty, non-comment lines)
HAS_DEPS=false
if [[ -f "$SCRIPT_DIR/requirements.txt" ]]; then
    if grep -qE '^[^#[:space:]]' "$SCRIPT_DIR/requirements.txt" 2>/dev/null; then
        HAS_DEPS=true
    fi
fi

# Detect whether playwright is a listed dependency (drives Chromium install below)
HAS_PLAYWRIGHT=false
if [[ "$HAS_DEPS" == true ]] && grep -qE '^[[:space:]]*playwright([[:space:]<>=!~]|$)' "$SCRIPT_DIR/requirements.txt" 2>/dev/null; then
    HAS_PLAYWRIGHT=true
fi

if [[ "$DRY_RUN" == true ]]; then
    if [[ ! -d "$VENV_DIR" ]]; then
        echo "   [would create] venv at $VENV_DIR"
    else
        echo "   [exists] venv at $VENV_DIR"
    fi
    if [[ "$HAS_DEPS" == true ]]; then
        echo "   [would install] packages from requirements.txt"
    else
        echo "   [no packages] requirements.txt is empty (stdlib only)"
    fi
    if [[ "$HAS_PLAYWRIGHT" == true ]]; then
        echo "   [would install] Playwright Chromium browser"
    fi
else
    # Create venv if it doesn't exist
    # Try system python3 first, fall back to Hermes's venv Python
    if [[ ! -d "$VENV_DIR" ]]; then
        echo "   Creating venv..."
        if python3 -m venv "$VENV_DIR" 2>/dev/null; then
            echo "   ✓ Created venv using system Python"
        elif [[ -f "$HERMES_HOME/hermes-agent/venv/bin/python3" ]]; then
            "$HERMES_HOME/hermes-agent/venv/bin/python3" -m venv "$VENV_DIR"
            echo "   ✓ Created venv using Hermes Python"
        else
            echo "   ERROR: No usable Python with venv support found"
            echo "   Install python3-venv or ensure Hermes Agent is installed"
            exit 1
        fi
    else
        echo "   ✓ Venv exists at $VENV_DIR"
    fi

    # Sanity-check the venv's python3 against pyvenv.cfg.
    # If the system python3 is upgraded after the venv was created, the
    # bin/python3 symlink can end up pointing at a different Python version
    # than the one pip installs packages for, so `import <pkg>` silently
    # fails even though `pip install` "succeeded".
    if [[ -f "$VENV_DIR/pyvenv.cfg" ]]; then
        EXPECTED_PYVER=$(awk -F'[= ]+' '/^version[[:space:]]*=/ {print $2}' "$VENV_DIR/pyvenv.cfg" | cut -d. -f1-2)
        ACTUAL_PYVER=$("$VENV_DIR/bin/python3" -c 'import sys;print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || echo "")
        if [[ -n "$EXPECTED_PYVER" && "$EXPECTED_PYVER" != "$ACTUAL_PYVER" ]]; then
            echo "   ⚠ Venv python mismatch: bin/python3 reports $ACTUAL_PYVER, pyvenv.cfg expects $EXPECTED_PYVER"
            if [[ -x "$VENV_DIR/bin/python$EXPECTED_PYVER" ]]; then
                ln -sfn "python$EXPECTED_PYVER" "$VENV_DIR/bin/python3"
                ACTUAL_PYVER=$("$VENV_DIR/bin/python3" -c 'import sys;print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || echo "")
                if [[ "$EXPECTED_PYVER" == "$ACTUAL_PYVER" ]]; then
                    echo "   ✓ Repaired bin/python3 symlink → python$EXPECTED_PYVER"
                fi
            fi
            if [[ "$EXPECTED_PYVER" != "$ACTUAL_PYVER" ]]; then
                echo "   ERROR: cannot repair venv. Delete $VENV_DIR and rerun ./deploy.sh to rebuild."
                exit 1
            fi
        fi
    fi

    # Upgrade pip
    "$VENV_DIR/bin/pip" install --upgrade pip -q 2>/dev/null

    # Install/update dependencies if any exist
    if [[ "$HAS_DEPS" == true ]]; then
        echo "   Installing packages from requirements.txt..."
        "$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q
        echo "   ✓ Packages installed"
    else
        echo "   ✓ No packages to install (stdlib only)"
    fi

    # Install Playwright's Chromium browser if playwright is a listed dep.
    # Idempotent: playwright skips download if the browser is already present.
    # Non-fatal: network blips shouldn't break the whole deploy.
    if [[ "$HAS_PLAYWRIGHT" == true ]]; then
        echo "   Ensuring Playwright Chromium is installed..."
        if "$VENV_DIR/bin/python3" -m playwright install chromium >/dev/null 2>&1; then
            echo "   ✓ Playwright Chromium ready"
        else
            echo "   ⚠ Playwright Chromium install failed (continuing; uploader will fall back to system Chrome)"
        fi
    fi

    # Show venv Python info
    echo "   Python: $($VENV_DIR/bin/python3 --version)"
fi

# --- Step 3: Update the cron jobs (all 3) ---
echo ""
echo "3. Updating cron jobs..."

# Array of cron config files to process
CRON_CONFIGS=(
    "$SCRIPT_DIR/cron_job.json"
    "$SCRIPT_DIR/cron_job_pins.json"
    "$SCRIPT_DIR/cron_job_uploader.json"
)

JOBS_UPDATED=0
for CONFIG_FILE in "${CRON_CONFIGS[@]}"; do
    if [[ ! -f "$CONFIG_FILE" ]]; then
        continue
    fi

    # Read the config (heredoc + env var — no shell-into-Python interpolation)
    CONFIG_SUMMARY=$(CONFIG_FILE="$CONFIG_FILE" python3 - <<'PY' 2>/dev/null
import json, os, sys
try:
    with open(os.environ["CONFIG_FILE"]) as f:
        cfg = json.load(f)
    print(cfg.get("name", ""))
    print(cfg.get("schedule", ""))
    print(cfg.get("script", ""))
except Exception:
    sys.exit(1)
PY
    ) || CONFIG_SUMMARY=""
    JOB_NAME=$(sed -n '1p' <<<"$CONFIG_SUMMARY")
    SCHEDULE=$(sed -n '2p' <<<"$CONFIG_SUMMARY")
    SCRIPT=$(sed -n '3p' <<<"$CONFIG_SUMMARY")

    if [[ -z "$JOB_NAME" ]] || [[ -z "$SCRIPT" ]]; then
        echo "   ⚠ Skipping $CONFIG_FILE (invalid format)"
        continue
    fi
    # Empty schedule means "no cron schedule" — the job stays in jobs.json
    # for manual invocation (hermes cron run <id>) or for subprocess-chaining
    # from a parent job, but the scheduler will never fire it on its own.

    # Look up the existing job by name OR by script basename (jobs.json may
    # store the absolute path, while configs store just the filename).
    JOB_ID=$(CRON_JOBS_PATH="$CRON_JOBS" JOB_NAME="$JOB_NAME" JOB_SCRIPT="$SCRIPT" \
             python3 - <<'PY' 2>/dev/null
import json, os
try:
    with open(os.environ["CRON_JOBS_PATH"]) as f:
        data = json.load(f)
except Exception:
    raise SystemExit(0)
want_name = os.environ.get("JOB_NAME", "")
want_script = os.path.basename(os.environ.get("JOB_SCRIPT", ""))
for job in data.get("jobs", []):
    job_script = os.path.basename(job.get("script", "") or "")
    if job.get("name") == want_name or (want_script and job_script == want_script):
        print(job["id"])
        break
PY
    ) || JOB_ID=""

    if [[ "$DRY_RUN" == true ]]; then
        SCHED_DISPLAY="${SCHEDULE:-<none>}"
        if [[ -n "$JOB_ID" ]]; then
            echo "   [would update] $JOB_NAME ($JOB_ID) → schedule: $SCHED_DISPLAY"
        else
            echo "   [would create] $JOB_NAME → schedule: $SCHED_DISPLAY"
        fi
        continue
    fi

    if [[ -n "$JOB_ID" ]]; then
        echo "   Found existing job: $JOB_ID ($JOB_NAME)"
        echo "   Updating prompt, schedule, and enabled flag..."

        CRON_JOBS_PATH="$CRON_JOBS" JOB_ID="$JOB_ID" CONFIG_FILE="$CONFIG_FILE" \
            python3 - <<'PY'
import json, os
from datetime import datetime, timezone

with open(os.environ["CRON_JOBS_PATH"]) as f:
    data = json.load(f)

with open(os.environ["CONFIG_FILE"]) as f:
    config = json.load(f)

job_id = os.environ["JOB_ID"]
for job in data.get("jobs", []):
    if job["id"] == job_id:
        job["prompt"] = config["prompt"]
        job["script"] = config.get("script", "")
        # Empty schedule -> clear the cron expression in jobs.json. The job entry
        # stays so it can be invoked manually, but the scheduler skips it.
        sched_expr = config.get("schedule") or ""
        if sched_expr:
            job["schedule"] = {"kind": "cron", "expr": sched_expr, "display": sched_expr}
            job["schedule_display"] = sched_expr
        else:
            job["schedule"] = {"kind": "cron", "expr": "", "display": ""}
            job["schedule_display"] = ""
            job["next_run_at"] = None
        if "deliver" in config:
            job["deliver"] = config["deliver"]
        if "enabled" in config:
            job["enabled"] = config["enabled"]
        break

data["updated_at"] = datetime.now(timezone.utc).isoformat()

with open(os.environ["CRON_JOBS_PATH"], "w") as f:
    json.dump(data, f, indent=2)

print(f"   ✓ Updated {config.get('name','')}")
PY
        JOBS_UPDATED=$((JOBS_UPDATED + 1))
    else
        echo "   ⚠ No existing job found for: $JOB_NAME"
        echo "     Create with: hermes cron create --name '$JOB_NAME' --schedule '$SCHEDULE' --script '$SCRIPT'"
    fi
done

if [[ "$DRY_RUN" == false ]]; then
    if [[ $JOBS_UPDATED -eq 0 ]]; then
        echo "   (No existing jobs updated. You may need to create them manually.)"
    else
        echo "   ($JOBS_UPDATED job(s) updated)"
    fi
fi

# --- Step 4: Verify ---
echo ""
echo "4. Verification..."
if [[ "$DRY_RUN" == false ]]; then
    if [[ -f "$HERMES_SCRIPTS/trending_tech_products.py" ]]; then
        echo "   ✓ Script installed at $HERMES_SCRIPTS/trending_tech_products.py"
    else
        echo "   ✗ Script not found!"
    fi

    if [[ -d "$VENV_DIR" && -f "$VENV_DIR/bin/python3" ]]; then
        echo "   ✓ Venv ready at $VENV_DIR"
    else
        echo "   ✗ Venv not found!"
    fi

    # Report status of every configured cron job, not just Job 1.
    if [[ -f "$CRON_JOBS" ]]; then
        for CONFIG_FILE in "${CRON_CONFIGS[@]}"; do
            [[ -f "$CONFIG_FILE" ]] || continue
            CRON_JOBS_PATH="$CRON_JOBS" CONFIG_FILE="$CONFIG_FILE" python3 - <<'PY'
import json, os
with open(os.environ["CRON_JOBS_PATH"]) as f:
    data = json.load(f)
with open(os.environ["CONFIG_FILE"]) as f:
    cfg = json.load(f)
want_name = cfg.get("name", "")
want_script = os.path.basename(cfg.get("script", "") or "")
for job in data.get("jobs", []):
    job_script = os.path.basename(job.get("script", "") or "")
    if job.get("name") == want_name or (want_script and job_script == want_script):
        status = "enabled" if job.get("enabled", True) else "disabled"
        print(f"   ✓ {job['name']} ({job['id']}) — {job.get('schedule_display','?')} [{status}]")
        break
else:
    print(f"   ✗ Not registered in jobs.json: {want_name}")
PY
        done
    fi

    # Non-destructive import check: validates syntax and that venv deps resolve
    # for all three job scripts, without triggering the live pipeline.
    echo ""
    echo "   Verifying job scripts import cleanly..."
    IMPORT_OK=true
    for MOD in trending_tech_products pinterest_pin_generator pinterest_pin_uploader; do
        if [[ ! -f "$HERMES_SCRIPTS/$MOD.py" ]]; then
            continue
        fi
        if IMPORT_ERR=$(cd "$HERMES_SCRIPTS" && "$VENV_DIR/bin/python3" -c "import $MOD" 2>&1); then
            echo "   ✓ $MOD imports cleanly"
        else
            echo "   ✗ $MOD failed to import:"
            echo "$IMPORT_ERR" | sed 's/^/       /'
            IMPORT_OK=false
        fi
    done
    if [[ "$IMPORT_OK" != true ]]; then
        echo "   ⚠ One or more scripts failed to import — check venv deps."
    fi
fi

echo ""
echo "Done! The cron job will use the updated script on its next run."
echo "To test now: hermes cron run <job_id>"
