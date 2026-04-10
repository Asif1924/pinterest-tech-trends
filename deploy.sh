#!/usr/bin/env bash
set -euo pipefail

# Pinterest Tech Trends - Deploy Script
# Syncs the scraper script and cron job config to Hermes Agent
#
# Usage:
#   ./deploy.sh           # Deploy script + update cron job
#   ./deploy.sh --dry-run # Show what would change without applying

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_SCRIPTS="$HERMES_HOME/scripts"
CRON_JOBS="$HERMES_HOME/cron/jobs.json"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "=== DRY RUN MODE ==="
fi

echo "Pinterest Tech Trends - Deploy"
echo "==============================="
echo "Source:     $SCRIPT_DIR"
echo "Hermes:     $HERMES_HOME"
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

# --- Deploy the scraper script ---
echo "1. Deploying scraper script..."
mkdir -p "$HERMES_SCRIPTS"

if [[ "$DRY_RUN" == true ]]; then
    if diff -q "$SCRIPT_DIR/trending_tech_products.py" "$HERMES_SCRIPTS/trending_tech_products.py" &>/dev/null; then
        echo "   [no changes] trending_tech_products.py"
    else
        echo "   [would update] trending_tech_products.py"
        diff "$HERMES_SCRIPTS/trending_tech_products.py" "$SCRIPT_DIR/trending_tech_products.py" || true
    fi
else
    cp "$SCRIPT_DIR/trending_tech_products.py" "$HERMES_SCRIPTS/trending_tech_products.py"
    echo "   ✓ Copied to $HERMES_SCRIPTS/trending_tech_products.py"
fi

# --- Update the cron job ---
echo ""
echo "2. Updating cron job..."

if [[ ! -f "$SCRIPT_DIR/cron_job.json" ]]; then
    echo "   WARNING: cron_job.json not found, skipping cron update"
else
    # Read the exported config
    JOB_NAME=$(python3 -c "import json; print(json.load(open('$SCRIPT_DIR/cron_job.json'))['name'])")
    SCHEDULE=$(python3 -c "import json; print(json.load(open('$SCRIPT_DIR/cron_job.json'))['schedule'])")
    PROMPT=$(python3 -c "import json; print(json.load(open('$SCRIPT_DIR/cron_job.json'))['prompt'])")

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

# --- Verify ---
echo ""
echo "3. Verification..."
if [[ "$DRY_RUN" == false ]]; then
    if [[ -f "$HERMES_SCRIPTS/trending_tech_products.py" ]]; then
        echo "   ✓ Script installed at $HERMES_SCRIPTS/trending_tech_products.py"
    else
        echo "   ✗ Script not found!"
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
fi

echo ""
echo "Done! The cron job will use the updated script on its next run."
echo "To test now: hermes cron run <job_id>"
