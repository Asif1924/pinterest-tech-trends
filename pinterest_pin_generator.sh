#!/usr/bin/env bash
# Cron entry-point shim for Job 2 (Pinterest Pin Generator).
# See trending_tech_products.sh for the rationale; this exists so manual
# `hermes cron run <pin_generator_id>` invocations also use the project venv.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/.venv/bin/python3" "$SCRIPT_DIR/pinterest_pin_generator.py" "$@"
