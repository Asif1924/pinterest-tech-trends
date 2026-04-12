#!/usr/bin/env python3
"""
Pinterest Pin Uploader - Data Collection Script

Scans pending pin files and outputs JSON for the agent to upload via browser.

All settings in pinterest_config.json — no hardcoded values.
Output: JSON to stdout with pending pins + credentials for the agent.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pinterest_config.json")


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


CFG = load_config()
PINS_DIR = os.path.join(HERMES_HOME, "pinterest_pins")
ENV_PATH = os.path.join(HERMES_HOME, ".env")
MAX_PINS_PER_RUN = CFG.get("max_pins_per_upload_batch", 5)
BOARD_NAME = CFG.get("pinterest", {}).get("board_name", "SmartyPants9786")
BOARD_URL = CFG.get("pinterest", {}).get("board_url", "")
PINS_FOLDER_ID = CFG.get("google_drive", {}).get("pins_folder_id", "")


def load_env():
    creds = {}
    try:
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    creds[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return creds


def get_pending_pins():
    os.makedirs(PINS_DIR, exist_ok=True)
    pending = []
    uploaded = 0
    failed = 0
    for f in sorted(Path(PINS_DIR).glob("pin_*.json")):
        try:
            with open(f) as fh:
                pin = json.load(fh)
            status = pin.get("status", "unknown")
            if status == "pending_upload":
                pin["_file_path"] = str(f)
                pin["_file_name"] = f.name
                pending.append(pin)
            elif status == "uploaded":
                uploaded += 1
            elif status == "failed":
                failed += 1
        except (json.JSONDecodeError, IOError):
            failed += 1
    return pending, uploaded, failed


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    env = load_env()
    pending, uploaded, failed = get_pending_pins()
    batch = pending[:MAX_PINS_PER_RUN]

    # Send Telegram notification
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_HOME_CHANNEL", "")
    if token and chat_id and pending:
        try:
            import urllib.request
            data = json.dumps({
                "chat_id": chat_id,
                "text": f"🚀 Job 3 started: Uploading {len(batch)} pins to Pinterest ({today})"
            }).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=data, headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=CFG.get("timeouts", {}).get("telegram_api", 10))
        except Exception:
            pass

    output = {
        "date": today,
        "pins_directory": PINS_DIR,
        "pinterest_email": env.get("PINTEREST_EMAIL", ""),
        "pinterest_password": env.get("PINTEREST_PASSWORD", ""),
        "telegram_bot_token": env.get("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": env.get("TELEGRAM_HOME_CHANNEL", ""),
        "google_token_path": os.path.join(HERMES_HOME, "google_token.json"),
        "drive_pins_folder_id": PINS_FOLDER_ID,
        "board_name": BOARD_NAME,
        "board_url": BOARD_URL,
        "stats": {
            "pending_upload": len(pending),
            "in_this_batch": len(batch),
            "already_uploaded": uploaded,
            "failed": failed,
            "remaining_after_batch": len(pending) - len(batch),
        },
        "batch": batch,
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
