#!/usr/bin/env python3
"""
Pinterest Pin Generator - Data Collection Script

Polls the PinterestAutomation folder on Google Drive, downloads the latest
trending tech products CSV, and outputs structured JSON for the cron job agent
to generate Pinterest pin files.

The agent will create individual pin JSON files in ~/.hermes/pinterest_pins/
that a separate job can use to upload to Pinterest.

Output: JSON to stdout with CSV data + metadata for the agent.
"""

# ── Venv bootstrap ──────────────────────────────────────────────────────────
import os
import sys
from pathlib import Path

# This script requires google-api-python-client which is installed in the
# Hermes venv. Since Hermes runs cron scripts via sys.executable (its own
# venv Python), no venv bootstrap is needed here.
# ── End venv bootstrap ──────────────────────────────────────────────────────

import csv
import json
import io
from datetime import datetime, timezone

# Google API imports — available in Hermes venv
try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
except ImportError:
    print(json.dumps({
        "error": "Google API libraries not installed. Run: pip install google-api-python-client google-auth-oauthlib",
        "products": []
    }))
    sys.exit(0)

HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
TOKEN_PATH = os.path.join(HERMES_HOME, "google_token.json")
DRIVE_FOLDER_ID = "1w-XAxZccQ4wk4NOKwm2YDusouLvO-a6L"
PINS_DIR = os.path.join(HERMES_HOME, "pinterest_pins")


def get_drive_service():
    """Authenticate and return a Google Drive service."""
    with open(TOKEN_PATH) as f:
        token_data = json.load(f)

    creds = Credentials(
        token=token_data["token"],
        refresh_token=token_data["refresh_token"],
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=token_data["scopes"],
    )

    if creds.expired:
        creds.refresh(Request())
        # Save refreshed token
        token_data["token"] = creds.token
        with open(TOKEN_PATH, "w") as f:
            json.dump(token_data, f, indent=2)

    return build("drive", "v3", credentials=creds)


def get_latest_csv(service):
    """Find and download the most recent CSV from the PinterestAutomation folder."""
    results = service.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and mimeType='text/csv' and trashed=false",
        orderBy="createdTime desc",
        pageSize=1,
        fields="files(id, name, createdTime, modifiedTime)",
    ).execute()

    files = results.get("files", [])
    if not files:
        return None, None

    latest = files[0]
    file_id = latest["id"]

    # Download the file content
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    csv_content = buffer.getvalue().decode("utf-8")
    return latest, csv_content


def parse_csv(csv_content):
    """Parse CSV content into a list of product dicts."""
    products = []
    reader = csv.DictReader(io.StringIO(csv_content))
    for row in reader:
        products.append({
            "number": row.get("Number", "").strip(),
            "name": row.get("Product Name", "").strip(),
            "category": row.get("Category", "").strip(),
            "description": row.get("Description", "").strip(),
            "why_trending": row.get("Why Trending", "").strip(),
            "price_range": row.get("Price Range", "").strip(),
            "amazon_link": row.get("Amazon Link", "").strip(),
            "pin_caption": row.get("Pin Caption Idea", "").strip(),
        })
    return products


def get_existing_pins():
    """Check which products already have pin files to avoid duplicates."""
    os.makedirs(PINS_DIR, exist_ok=True)
    existing = set()
    for f in os.listdir(PINS_DIR):
        if f.endswith(".json"):
            try:
                with open(os.path.join(PINS_DIR, f)) as fh:
                    pin = json.load(fh)
                    existing.add(pin.get("product_name", ""))
            except (json.JSONDecodeError, IOError):
                pass
    return existing


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        service = get_drive_service()
    except Exception as e:
        print(json.dumps({"error": f"Drive auth failed: {e}", "products": []}))
        return

    try:
        file_info, csv_content = get_latest_csv(service)
    except Exception as e:
        print(json.dumps({"error": f"Drive download failed: {e}", "products": []}))
        return

    if not file_info or not csv_content:
        print(json.dumps({
            "error": "No CSV files found in PinterestAutomation folder",
            "products": [],
        }))
        return

    products = parse_csv(csv_content)
    existing_pins = get_existing_pins()

    # Filter out products that already have pins
    new_products = [p for p in products if p["name"] not in existing_pins]

    output = {
        "date": today,
        "source_file": {
            "id": file_info["id"],
            "name": file_info["name"],
            "created": file_info.get("createdTime", ""),
            "modified": file_info.get("modifiedTime", ""),
        },
        "total_products": len(products),
        "new_products": len(new_products),
        "already_pinned": len(products) - len(new_products),
        "pins_directory": PINS_DIR,
        "products": new_products,
        "all_categories": list(set(p["category"] for p in products if p["category"])),
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
