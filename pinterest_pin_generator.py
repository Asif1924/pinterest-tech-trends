#!/usr/bin/env python3
"""
Pinterest Pin Generator — FULLY AUTOMATED (no AI needed)

Polls Google Drive PinterestAutomation folder, downloads the latest CSV,
creates Pinterest pin JSON files, uploads them to Drive Pins folder.

All settings in pinterest_config.json — no hardcoded values.
Output: Plain text summary to stdout.
Cost: $0 per run.
"""

import os
import sys
import csv
import io
import json
from pathlib import Path
from datetime import datetime, timezone

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
except ImportError:
    print("ERROR: Google API libraries not installed.")
    sys.exit(1)

# ── Config ──────────────────────────────────────────────────────────────────
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
DRIVE_FOLDER_ID = CFG.get("google_drive", {}).get("automation_folder_id", "")
PINS_FOLDER_ID = CFG.get("google_drive", {}).get("pins_folder_id", "")
BOARD_NAME = CFG.get("pinterest", {}).get("board_name", "SmartyPants9786")
TIMEOUT_TELEGRAM = CFG.get("timeouts", {}).get("telegram_api", 10)

HASHTAGS = {
    "Smart Home and IoT": "#SmartHome #IoT #HomeAutomation #TechHome #GadgetGoals",
    "Phone and Tablet Accessories": "#PhoneTech #MobileGadgets #SmartphoneAccessories #TechAccessories",
    "Audio and Wearables": "#AudioTech #Wearables #Earbuds #SmartWatch #TechWearables",
    "Cool Gadgets and Gizmos": "#CoolGadgets #TechGadgets #GadgetLover #Innovation #MustHave",
    "PC and Gaming Tech": "#GamingTech #PCGaming #GamingSetup #TechDeals #PCBuild",
}


# ── Telegram ────────────────────────────────────────────────────────────────

def _load_env_var(name):
    try:
        with open(os.path.join(HERMES_HOME, ".env")) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() == name:
                        return v.strip()
    except FileNotFoundError:
        pass
    return ""


def send_telegram(text):
    import urllib.request as _ur
    token = _load_env_var("TELEGRAM_BOT_TOKEN")
    chat_id = _load_env_var("TELEGRAM_HOME_CHANNEL")
    if not token or not chat_id:
        return
    try:
        data = json.dumps({"chat_id": chat_id, "text": text}).encode()
        req = _ur.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, headers={"Content-Type": "application/json"}
        )
        _ur.urlopen(req, timeout=TIMEOUT_TELEGRAM)
    except Exception:
        pass


# ── Google Drive ────────────────────────────────────────────────────────────

def get_drive_service():
    token_path = os.path.join(HERMES_HOME, "google_token.json")
    with open(token_path) as f:
        td = json.load(f)
    creds = Credentials(
        token=td["token"], refresh_token=td["refresh_token"],
        token_uri=td["token_uri"], client_id=td["client_id"],
        client_secret=td["client_secret"], scopes=td["scopes"],
    )
    if creds.expired:
        creds.refresh(Request())
        td["token"] = creds.token
        with open(token_path, "w") as f:
            json.dump(td, f, indent=2)
    return build("drive", "v3", credentials=creds)


def ensure_pins_folder(service):
    global PINS_FOLDER_ID
    if PINS_FOLDER_ID:
        try:
            service.files().get(fileId=PINS_FOLDER_ID, fields="id,trashed").execute()
            return PINS_FOLDER_ID
        except Exception:
            pass
    results = service.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and name='Pins' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id)",
    ).execute()
    if results.get("files"):
        PINS_FOLDER_ID = results["files"][0]["id"]
        return PINS_FOLDER_ID
    folder = service.files().create(body={
        "name": "Pins", "mimeType": "application/vnd.google-apps.folder",
        "parents": [DRIVE_FOLDER_ID],
    }, fields="id").execute()
    PINS_FOLDER_ID = folder["id"]
    return PINS_FOLDER_ID


def get_latest_csv(service):
    results = service.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and mimeType='text/csv' and trashed=false",
        orderBy="createdTime desc", pageSize=1,
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


def cleanup_old_pins_local():
    os.makedirs(PINS_DIR, exist_ok=True)
    count = 0
    for f in Path(PINS_DIR).glob("pin_*.json"):
        f.unlink()
        count += 1
    return count


def cleanup_old_pins_drive(service):
    count = 0
    page_token = None
    while True:
        results = service.files().list(
            q=f"'{PINS_FOLDER_ID}' in parents and trashed=false",
            fields="nextPageToken, files(id, name)", pageSize=100, pageToken=page_token,
        ).execute()
        for f in results.get("files", []):
            service.files().delete(fileId=f["id"]).execute()
            count += 1
        page_token = results.get("nextPageToken")
        if not page_token:
            break
    return count


def cleanup_old_csvs_drive(service, keep_latest=1):
    results = service.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and mimeType='text/csv' and trashed=false",
        orderBy="createdTime desc", fields="files(id, name, createdTime)", pageSize=50,
    ).execute()
    files = results.get("files", [])
    deleted = 0
    for f in files[keep_latest:]:
        service.files().delete(fileId=f["id"]).execute()
        deleted += 1
    return deleted


def upload_pin_to_drive(service, pin_path, pin_filename):
    file_metadata = {
        "name": pin_filename, "parents": [PINS_FOLDER_ID],
        "mimeType": "application/json",
    }
    media = MediaFileUpload(pin_path, mimetype="application/json")
    existing = service.files().list(
        q=f"name='{pin_filename}' and '{PINS_FOLDER_ID}' in parents and trashed=false",
        fields="files(id)",
    ).execute().get("files", [])
    if existing:
        file = service.files().update(fileId=existing[0]["id"], media_body=media, fields="id").execute()
    else:
        file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    return file["id"]


# ── Pin Creation ────────────────────────────────────────────────────────────

def parse_csv(csv_content):
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


def create_pin_json(product, date_str):
    name = product["name"]
    category = product["category"]
    price = product["price_range"]
    description = product["description"]
    caption = product["pin_caption"]
    link = product["amazon_link"]
    image_1 = product["image_1"]
    image_2 = product["image_2"]

    category_tags = HASHTAGS.get(category, "#TechGadgets #Innovation")
    pin_description = caption if caption else f"{name} - {description}"
    if category_tags not in pin_description:
        pin_description = f"{pin_description} {category_tags}"
    pin_description = pin_description[:500]
    title = f"{name} - {price}" if price else name
    title = title[:100]

    images = []
    if image_1:
        images.append({"url": image_1, "size": "large"})
    if image_2:
        images.append({"url": image_2, "size": "large"})

    return {
        "product_name": name, "board": BOARD_NAME.lower(),
        "title": title, "description": pin_description,
        "link": link, "category": category,
        "alt_text": f"Product image of {name} - {description[:100]}",
        "images": images,
        "primary_image": image_1 or image_2 or "",
        "price_range": price,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending_upload",
    }


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    today = datetime.now(timezone.utc)
    date_str = today.strftime("%Y%m%d")

    send_telegram(f"📌 Job 2 started: Generating Pinterest pins ({today.strftime('%Y-%m-%d')})")

    try:
        service = get_drive_service()
    except Exception as e:
        print(f"ERROR: Google Drive auth failed: {e}")
        return

    try:
        file_info, csv_content = get_latest_csv(service)
    except Exception as e:
        print(f"ERROR: Failed to download CSV from Drive: {e}")
        return

    if not file_info or not csv_content:
        print("[SILENT]")
        return

    products = parse_csv(csv_content)
    if not products:
        print("[SILENT]")
        return

    # Ensure Pins folder exists, then clean up
    ensure_pins_folder(service)
    local_deleted = cleanup_old_pins_local()
    drive_pins_deleted = cleanup_old_pins_drive(service)
    old_csvs_deleted = cleanup_old_csvs_drive(service, keep_latest=1)
    new_products = products

    # Create pin files and upload to Drive
    created = []
    uploaded = []
    errors = []

    for product in new_products:
        num = product["number"].zfill(2)
        filename = f"pin_{date_str}_{num}.json"
        filepath = os.path.join(PINS_DIR, filename)
        try:
            pin_data = create_pin_json(product, date_str)
            with open(filepath, "w") as f:
                json.dump(pin_data, f, indent=2)
            created.append((filename, product["name"]))
            drive_id = upload_pin_to_drive(service, filepath, filename)
            uploaded.append((filename, product["name"], drive_id))
        except Exception as e:
            errors.append((product["name"], str(e)))

    # Output summary
    print(f"Pinterest Pin Generator Report - {today.strftime('%B %d, %Y')}")
    print(f"Source CSV: {file_info['name']}")
    print()
    print(f"Cleanup:")
    print(f"  Old local pins deleted: {local_deleted}")
    print(f"  Old Drive pins deleted: {drive_pins_deleted}")
    print(f"  Old CSVs deleted: {old_csvs_deleted}")
    print()
    print(f"Created: {len(created)} pin files")
    print(f"Uploaded to Drive: {len(uploaded)} files")
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

    send_telegram(f"✅ Job 2 complete: {len(created)} pins created, {len(uploaded)} uploaded to Drive")


if __name__ == "__main__":
    main()
