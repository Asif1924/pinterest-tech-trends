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
    if diff -q "$SCRIPT_DIR/trending_tech_products.py" "$HERMES_SCRIPTS/trending_tech_products.py" &>/dev/null; then
        echo "   [no changes] trending_tech_products.py"
    else
        echo "   [would update] trending_tech_products.py"
    fi
else
    cp "$SCRIPT_DIR/trending_tech_products.py" "$HERMES_SCRIPTS/trending_tech_products.py"
    echo "   ✓ Copied to $HERMES_SCRIPTS/trending_tech_products.py"
    if [[ -f "$SCRIPT_DIR/config.json" ]]; then
        cp "$SCRIPT_DIR/config.json" "$HERMES_SCRIPTS/pinterest_config.json"
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

    # Show venv Python info
    echo "   Python: $($VENV_DIR/bin/python3 --version)"
fi

# --- Step 3: Update the cron job ---
echo ""
echo "3. Updating cron job..."

if [[ ! -f "$SCRIPT_DIR/cron_job.json" ]]; then
    echo "   WARNING: cron_job.json not found, skipping cron update"
else
    # Read the exported config
    JOB_NAME=$(python3 -c "import json; print(json.load(open('$SCRIPT_DIR/cron_job.json'))['name'])")
    SCHEDULE=$(python3 -c "import json; print(json.load(open('$SCRIPT_DIR/cron_job.json'))['schedule'])")

    if [[ "$DRY_RUN" == true ]]; then
        echo "   [would update] cron job: $JOB_NAME"
        echo "   Schedule: $SCHEDULE"
    else
        # Find existing job ID
        JOB_ID=$(python3 -c "
import json
with open('$CRON_JOBS') as f:
    data = json.load(f)
for job in data.get('jobs', []):
    if job.get('name') == '$JOB_NAME' or job.get('script') == 'trending_tech_products.py':
        print(job['id'])
        break
" 2>/dev/null || echo "")

        if [[ -n "$JOB_ID" ]]; then
            echo "   Found existing job: $JOB_ID"
            echo "   Updating prompt and schedule..."

            python3 -c "
import json
with open('$CRON_JOBS') as f:
    data = json.load(f)
config = json.load(open('$SCRIPT_DIR/cron_job.json'))
for job in data.get('jobs', []):
    if job['id'] == '$JOB_ID':
        job['prompt'] = config['prompt']
        job['script'] = config.get('script', 'trending_tech_products.py')
        job['schedule'] = {'kind': 'cron', 'expr': config['schedule'], 'display': config['schedule']}
        job['schedule_display'] = config['schedule']
        break
from datetime import datetime, timezone
data['updated_at'] = datetime.now(timezone.utc).isoformat()
with open('$CRON_JOBS', 'w') as f:
    json.dump(data, f, indent=2)
print('   ✓ Cron job updated')
"
        else
            echo "   No existing job found. Create one with:"
            echo "   hermes cron create --name '$JOB_NAME' --schedule '$SCHEDULE' --script trending_tech_products.py"
        fi
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

    if [[ -f "$CRON_JOBS" ]]; then
        python3 -c "
import json
with open('$CRON_JOBS') as f:
    data = json.load(f)
for job in data.get('jobs', []):
    if job.get('script') == 'trending_tech_products.py':
        print(f'   ✓ Cron job active: {job[\"name\"]} (ID: {job[\"id\"]})')
        print(f'     Schedule: {job.get(\"schedule_display\", \"?\")}')
        print(f'     Deliver:  {job.get(\"deliver\", \"?\")}')
        break
"
    fi

    # Test the script runs
    echo ""
    echo "   Testing script execution..."
    RESULT=$("$VENV_DIR/bin/python3" "$HERMES_SCRIPTS/trending_tech_products.py" 2>&1 | head -1)
    if echo "$RESULT" | grep -q '"date"'; then
        echo "   ✓ Script runs successfully in venv"
    else
        echo "   ⚠ Script output unexpected: $RESULT"
    fi
fi

echo ""
echo "Done! The cron job will use the updated script on its next run."
echo "To test now: hermes cron run <job_id>"
