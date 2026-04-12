#!/usr/bin/env python3
"""
Pinterest Pin Uploader - Data Collection Script

Scans ~/.hermes/pinterest_pins/ for pin JSON files with status "pending_upload",
reads them, and outputs structured JSON for the cron job agent to upload to Pinterest.

The agent will use the Pinterest API to create pins on the SmartyPants9786 board,
then update each pin file's status to "uploaded".

Output: JSON to stdout with pending pins data for the agent.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
PINS_DIR = os.path.join(HERMES_HOME, "pinterest_pins")
ENV_PATH = os.path.join(HERMES_HOME, ".env")


def load_env_var(name):
    """Read a variable from ~/.hermes/.env."""
    try:
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    if key.strip() == name:
                        return val.strip()
    except FileNotFoundError:
        pass
    return ""


def get_pending_pins():
    """Find all pin files with status 'pending_upload'."""
    os.makedirs(PINS_DIR, exist_ok=True)
    pending = []
    uploaded = []
    failed = []
    
    pin_files = sorted(Path(PINS_DIR).glob("pin_*.json"))
    
    for pin_path in pin_files:
        try:
            with open(pin_path) as f:
                pin = json.load(f)
            
            status = pin.get("status", "unknown")
            if status == "pending_upload":
                pin["_file_path"] = str(pin_path)
                pin["_file_name"] = pin_path.name
                pending.append(pin)
            elif status == "uploaded":
                uploaded.append(pin_path.name)
            elif status == "failed":
                failed.append(pin_path.name)
        except (json.JSONDecodeError, IOError) as e:
            failed.append(f"{pin_path.name}: {e}")
    
    return pending, uploaded, failed


def check_pinterest_credentials():
    """Check if Pinterest API credentials are configured."""
    app_id = load_env_var("PINTEREST_APP_ID")
    app_secret = load_env_var("PINTEREST_APP_SECRET")
    access_token = load_env_var("PINTEREST_ACCESS_TOKEN")
    
    return {
        "app_id_set": bool(app_id),
        "app_secret_set": bool(app_secret),
        "access_token_set": bool(access_token),
        "ready": bool(access_token),
    }


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    pending, uploaded, failed = get_pending_pins()
    creds = check_pinterest_credentials()
    
    output = {
        "date": today,
        "pins_directory": PINS_DIR,
        "credentials": creds,
        "stats": {
            "pending_upload": len(pending),
            "already_uploaded": len(uploaded),
            "failed": len(failed),
        },
        "pending_pins": pending,
        "already_uploaded_files": uploaded,
        "failed_files": failed,
        "board_name": "SmartyPants9786",
        "env_path": ENV_PATH,
    }
    
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
