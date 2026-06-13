#!/usr/bin/env bash
# Cron entry-point shim for Job 1 (Trending Tech Products).
#
# Hermes' cron runner picks the interpreter by extension (.sh/.bash -> bash,
# anything else -> sys.executable, which is Hermes' own venv). We use a .sh
# shim so cron actually invokes the project venv (with scrapling, playwright,
# undetected-chromedriver, etc.) instead of Hermes' own interpreter, which
# does not ship with those packages.
#
# Once this exec's into the project venv's python3, sys.executable inside
# Job 1 points at the project venv, so the chained subprocess.run calls
# (Job 1 -> Job 2 -> Job 3) automatically inherit the same interpreter.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/.venv/bin/python3" "$SCRIPT_DIR/trending_tech_products.py" "$@"
