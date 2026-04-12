#!/usr/bin/env python3
"""
Pinterest Pin Generator — FULLY AUTOMATED (no AI needed)

Polls Google Drive PinterestAutomation folder, downloads the latest CSV,
creates Pinterest pin JSON files for new products, uploads them to
Google Drive PinterestAutomation/Pins folder, and outputs a summary.

This script does everything — no agent turn required.
The cron job just delivers the script's stdout to Telegram.

Output: Plain text summary to stdout (delivered to Telegram by Hermes).
"""

import os
import sys
import csv
import io
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

# Google API imports
try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
except ImportError:
    print("ERROR: Google API libraries not installed.")
    print("Run: pip install google-api-python-client google-auth-oauthlib")
    sys.exit(1)

HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
TOKEN_PATH = os.path.join(HERMES_HOME, "google_token.json")
PINS_DIR = os.path.join(HERMES_HOME, "pinterest_pins")
DRIVE_FOLDER_ID = "1w-XAxZccQ4wk4NOKwm2YDusouLvO-a6L"  # PinterestAutomation
PINS_FOLDER_ID = "1sggNrixmH_jWFTLhspoy3i3YM7GVir7I"   # PinterestAutomation/Pins
BOARD_NAME = "smartypants9786"

# Hashtag map by category
HASHTAGS = {
    "Smart Home and IoT": "#SmartHome #IoT #HomeAutomation #TechHome #GadgetGoals",
    "Phone and Tablet Accessories": "#PhoneTech #MobileGadgets #SmartphoneAccessories #TechAccessories",
    "Audio and Wearables": "#AudioTech #Wearables #Earbuds #SmartWatch #TechWearables",
    "Cool Gadgets and Gizmos": "#CoolGadgets #TechGadgets #GadgetLover #Innovation #MustHave",
    "PC and Gaming Tech": "#GamingTech #PCGaming #GamingSetup #TechDeals #PCBuild",
}


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
        fields="files(id, name, createdTime)",
    ).execute()

    files = results.get("files", [])
    if not files:
        return None, None

    latest = files[0]
    request = service.files().get_media(fileId=latest["id"])
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    return latest, buffer.getvalue().decode("utf-8")


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
            "image_1": row.get("Image 1", "").strip(),
            "image_2": row.get("Image 2", "").strip(),
        })
    return products


def get_existing_pin_names():
    """Get product names that already have pin files."""
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


def create_pin_json(product, date_str):
    """Create a pin JSON dict from product data."""
    name = product["name"]
    category = product["category"]
    price = product["price_range"]
    description = product["description"]
    caption = product["pin_caption"]
    link = product["amazon_link"]
    image_1 = product["image_1"]
    image_2 = product["image_2"]

    # Build hashtags
    category_tags = HASHTAGS.get(category, "#TechGadgets #Innovation")

    # Build description with hashtags (max 500 chars)
    pin_description = caption if caption else f"{name} - {description}"
    if category_tags not in pin_description:
        pin_description = f"{pin_description} {category_tags}"
    pin_description = pin_description[:500]

    # Build title (max 100 chars)
    title = f"{name} - {price}" if price else name
    title = title[:100]

    # Build images array
    images = []
    if image_1:
        images.append({"url": image_1, "size": "large"})
    if image_2:
        images.append({"url": image_2, "size": "large"})

    return {
        "product_name": name,
        "board": BOARD_NAME,
        "title": title,
        "description": pin_description,
        "link": link,
        "category": category,
        "alt_text": f"Product image of {name} - {description[:100]}",
        "images": images,
        "primary_image": image_1 or image_2 or "",
        "price_range": price,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending_upload",
    }


def upload_pin_to_drive(service, pin_path, pin_filename):
    """Upload a pin JSON file to the Drive Pins folder."""
    file_metadata = {
        "name": pin_filename,
        "parents": [PINS_FOLDER_ID],
        "mimeType": "application/json",
    }
    media = MediaFileUpload(pin_path, mimetype="application/json")
    
    # Check if file already exists in Drive (by name)
    existing = service.files().list(
        q=f"name='{pin_filename}' and '{PINS_FOLDER_ID}' in parents and trashed=false",
        fields="files(id)",
    ).execute().get("files", [])
    
    if existing:
        # Update existing file
        file = service.files().update(
            fileId=existing[0]["id"],
            media_body=media,
            fields="id",
        ).execute()
    else:
        # Create new file
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id",
        ).execute()
    
    return file["id"]


def main():
    today = datetime.now(timezone.utc)
    date_str = today.strftime("%Y%m%d")

    # Step 1: Connect to Drive
    try:
        service = get_drive_service()
    except Exception as e:
        print(f"ERROR: Google Drive auth failed: {e}")
        return

    # Step 2: Download latest CSV
    try:
        file_info, csv_content = get_latest_csv(service)
    except Exception as e:
        print(f"ERROR: Failed to download CSV from Drive: {e}")
        return

    if not file_info or not csv_content:
        print("[SILENT]")
        return

    # Step 3: Parse CSV
    products = parse_csv(csv_content)
    if not products:
        print("[SILENT]")
        return

    # Step 4: Check for already-pinned products
    existing = get_existing_pin_names()
    new_products = [p for p in products if p["name"] not in existing]

    if not new_products:
        print("[SILENT]")
        return

    # Step 5: Create pin files and upload to Drive
    created = []
    uploaded = []
    errors = []

    for product in new_products:
        num = product["number"].zfill(2)
        filename = f"pin_{date_str}_{num}.json"
        filepath = os.path.join(PINS_DIR, filename)

        try:
            # Create pin JSON
            pin_data = create_pin_json(product, date_str)
            with open(filepath, "w") as f:
                json.dump(pin_data, f, indent=2)
            created.append((filename, product["name"]))

            # Upload to Drive
            drive_id = upload_pin_to_drive(service, filepath, filename)
            uploaded.append((filename, product["name"], drive_id))

        except Exception as e:
            errors.append((product["name"], str(e)))

    # Step 6: Output summary (delivered to Telegram)
    print(f"Pinterest Pin Generator Report - {today.strftime('%B %d, %Y')}")
    print(f"Source CSV: {file_info['name']}")
    print()
    print(f"Created: {len(created)} pin files")
    print(f"Uploaded to Drive: {len(uploaded)} files")
    print(f"Skipped (already pinned): {len(existing)} products")
    if errors:
        print(f"Errors: {len(errors)}")
        for name, err in errors:
            print(f"  - {name}: {err}")
    print()

    if created:
        print("Pins created:")
        for filename, name in created:
            has_img = "img" if any(p["name"] == name and (p["image_1"] or p["image_2"]) for p in new_products) else "no-img"
            print(f"  {filename}: {name} [{has_img}]")

    print()
    print(f"Local: {PINS_DIR}")
    print(f"Drive: PinterestAutomation/Pins/")


if __name__ == "__main__":
    main()
