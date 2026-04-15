#!/usr/bin/env python3
"""
Pinterest Pin Uploader — Multi-Method Upload

Uploads pending pins to Pinterest using three methods (in order):
  1. Pinterest API v5 (POST /v5/pins) — most reliable, requires access token
  2. Selenium browser automation — fallback, requires Chrome + credentials
  3. Email CSV for manual upload — final fallback, always works

Requires in ~/.hermes/.env:
  PINTEREST_ACCESS_TOKEN  — for API method (from developers.pinterest.com)
  PINTEREST_BOARD_ID      — board ID for API method
  PINTEREST_EMAIL         — for Selenium method
  PINTEREST_PASSWORD      — for Selenium method
  EMAIL_ADDRESS           — for email fallback
  EMAIL_PASSWORD          — for email fallback
"""

import json
import csv
import os
import sys
import smtplib
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pinterest_config.json")
PINS_DIR = Path(HERMES_HOME) / "pinterest_pins"
UPLOAD_BATCH_SIZE = 20
PINTEREST_API_URL = "https://api.pinterest.com/v5/pins"


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


CFG = load_config()


def load_env():
    env = {}
    try:
        with open(os.path.join(HERMES_HOME, ".env")) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env


def log(message):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{timestamp}] {message}")


def send_telegram(text, env):
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_HOME_CHANNEL", "")
    if not token or not chat_id:
        return
    try:
        data = json.dumps({"chat_id": chat_id, "text": text}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


# ── Load Pins ───────────────────────────────────────────────────────────────

def load_pending_pins():
    if not PINS_DIR.exists():
        log("No pinterest_pins directory found")
        return []
    pending = []
    for json_file in sorted(PINS_DIR.glob("*.json")):
        try:
            with open(json_file) as f:
                pin = json.load(f)
            if pin.get("status") in ("pending_upload", "ready_for_upload"):
                pin["_file_path"] = str(json_file)
                pending.append(pin)
        except Exception as e:
            log(f"Error reading {json_file.name}: {e}")
    log(f"Found {len(pending)} pins ready for upload")
    return pending


def mark_pin_status(pin, status):
    try:
        pin["status"] = status
        pin["uploaded_at"] = datetime.now(timezone.utc).isoformat()
        file_path = pin.get("_file_path")
        if file_path:
            save_data = {k: v for k, v in pin.items() if k != "_file_path"}
            with open(file_path, "w") as f:
                json.dump(save_data, f, indent=2)
    except Exception as e:
        log(f"Error updating pin status: {e}")


# ── Method 1: Pinterest API v5 ─────────────────────────────────────────────

def upload_via_api(pins, env):
    """Upload pins using Pinterest API v5. Returns (uploaded, failed) or None."""
    access_token = env.get("PINTEREST_ACCESS_TOKEN", "")
    board_id = env.get("PINTEREST_BOARD_ID", "")
    if not access_token or not board_id:
        log("API: Missing PINTEREST_ACCESS_TOKEN or PINTEREST_BOARD_ID — skipping")
        return None

    log(f"API: Uploading {len(pins)} pins to board {board_id}")
    uploaded, failed = [], []

    for pin in pins:
        image_url = pin.get("primary_image", "")
        if not image_url and pin.get("images"):
            image_url = pin["images"][0].get("url", "")
        if not image_url:
            log(f"  ⏭️ {pin.get('product_name', '?')}: no image — skipped")
            failed.append((pin, "no image URL"))
            continue

        payload = json.dumps({
            "board_id": board_id,
            "title": pin.get("title", "")[:100],
            "description": pin.get("description", "")[:500],
            "link": pin.get("link", ""),
            "alt_text": pin.get("alt_text", "")[:500],
            "media_source": {"source_type": "image_url", "url": image_url},
        }).encode()

        req = urllib.request.Request(
            PINTEREST_API_URL, data=payload, method="POST",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
            log(f"  ✅ {pin.get('product_name', '?')} → pin ID {result.get('id')}")
            mark_pin_status(pin, "uploaded")
            uploaded.append(pin)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:200]
            log(f"  ❌ {pin.get('product_name', '?')}: HTTP {e.code} — {body}")
            failed.append((pin, f"HTTP {e.code}: {body}"))
        except Exception as e:
            log(f"  ❌ {pin.get('product_name', '?')}: {e}")
            failed.append((pin, str(e)))

    return uploaded, failed


# ── Method 2: Selenium Browser Automation ───────────────────────────────────

def upload_via_browser(pins, env):
    """Upload pins via Selenium headless Chrome. Returns (uploaded, failed) or None."""
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.chrome.options import Options
    except ImportError:
        log("Browser: Selenium not installed — skipping")
        return None

    chrome_paths = ["/usr/bin/google-chrome", "/usr/bin/chromium-browser", "/usr/bin/chromium"]
    chrome_binary = next((p for p in chrome_paths if Path(p).exists()), None)
    if not chrome_binary:
        log("Browser: Chrome/Chromium not found — skipping")
        return None

    email = env.get("PINTEREST_EMAIL", "")
    password = env.get("PINTEREST_PASSWORD", "")
    if not email or not password:
        log("Browser: Missing PINTEREST_EMAIL or PINTEREST_PASSWORD — skipping")
        return None

    driver = None
    try:
        opts = Options()
        opts.binary_location = chrome_binary
        for arg in ["--no-sandbox", "--disable-dev-shm-usage", "--headless",
                     "--window-size=1920,1080", "--disable-gpu"]:
            opts.add_argument(arg)
        driver = webdriver.Chrome(options=opts)

        # Login
        log("Browser: Logging into Pinterest...")
        driver.get("https://www.pinterest.com/login/")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "email"))
        ).send_keys(email)
        driver.find_element(By.ID, "password").send_keys(password)
        driver.find_element(
            By.CSS_SELECTOR, "[data-test-id='registerFormSubmitButton']"
        ).click()
        WebDriverWait(driver, 15).until(EC.url_contains("pinterest.com/"))
        log("Browser: Login successful")

        # Upload each pin individually via pin builder
        uploaded, failed = [], []
        import time
        for pin in pins:
            image_url = pin.get("primary_image", "")
            if not image_url and pin.get("images"):
                image_url = pin["images"][0].get("url", "")
            if not image_url:
                failed.append((pin, "no image URL"))
                continue
            try:
                driver.get("https://www.pinterest.com/pin-creation-tool/")
                time.sleep(3)

                # Try to fill in the pin details
                # Upload image via URL if possible
                title_input = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-test-id='pin-draft-title'] textarea, [placeholder*='title' i]"))
                )
                title_input.clear()
                title_input.send_keys(pin.get("title", "")[:100])

                desc_input = driver.find_element(By.CSS_SELECTOR, "[data-test-id='pin-draft-description'] textarea, [placeholder*='description' i]")
                desc_input.clear()
                desc_input.send_keys(pin.get("description", "")[:500])

                link_input = driver.find_element(By.CSS_SELECTOR, "[data-test-id='pin-draft-link'] input, [placeholder*='link' i]")
                link_input.clear()
                link_input.send_keys(pin.get("link", ""))

                alt_input = driver.find_element(By.CSS_SELECTOR, "[data-test-id='pin-draft-alt-text'] textarea, [placeholder*='alt' i]")
                alt_input.clear()
                alt_input.send_keys(pin.get("alt_text", "")[:500])

                # Click publish
                publish_btn = driver.find_element(By.CSS_SELECTOR, "[data-test-id='board-dropdown-save-button'], button[type='submit']")
                publish_btn.click()
                time.sleep(3)

                log(f"  ✅ {pin.get('product_name', '?')}: published via browser")
                mark_pin_status(pin, "uploaded")
                uploaded.append(pin)
            except Exception as e:
                log(f"  ❌ {pin.get('product_name', '?')}: {e}")
                failed.append((pin, str(e)))

        driver.quit()
        return uploaded, failed

    except Exception as e:
        log(f"Browser: Upload failed — {e}")
        if driver:
            driver.quit()
        return None


# ── Method 3: Email CSV for Manual Upload ───────────────────────────────────

def create_bulk_csv(pins):
    """Create Pinterest-compatible CSV. Returns path."""
    csv_path = Path(HERMES_HOME) / f"pinterest_upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Media", "Board", "Title", "Description", "Link", "Alt text"])
        board = CFG.get("pinterest", {}).get("board_name", "SmartyPants9786").lower()
        for pin in pins:
            image_url = pin.get("primary_image", "")
            if not image_url and pin.get("images"):
                image_url = pin["images"][0].get("url", "")
            description = pin.get("description", "")
            if len(description) > 500:
                description = description[:497] + "..."
            writer.writerow([
                image_url, board, pin.get("title", ""),
                description, pin.get("link", ""), pin.get("alt_text", ""),
            ])
    return str(csv_path)


def upload_via_email(pins, env):
    """Email CSV as final fallback. Always returns ([], pins) since nothing is auto-uploaded."""
    email_addr = env.get("EMAIL_ADDRESS", "")
    email_pass = env.get("EMAIL_PASSWORD", "")
    if not email_addr or not email_pass:
        log("Email: Missing EMAIL_ADDRESS or EMAIL_PASSWORD — cannot send")
        return [], [(p, "email creds missing") for p in pins]

    csv_path = create_bulk_csv(pins)
    log(f"Email: Created bulk CSV at {csv_path}")

    msg = MIMEMultipart()
    msg["From"] = email_addr
    msg["To"] = email_addr
    msg["Subject"] = f"Pinterest Bulk Upload CSV — {len(pins)} pins ready"

    body = f"""Pinterest Bulk Upload — {datetime.now().strftime('%B %d, %Y')}

{len(pins)} pins are attached as a CSV for manual upload.

Upload instructions:
1. Go to https://business.pinterest.com/hub/
2. Click "Create" → "Bulk create Pins"
3. Upload the attached CSV file
4. Review and click "Create Pins"

Pins included:
"""
    for i, pin in enumerate(pins, 1):
        body += f"  {i}. {pin.get('product_name', '?')}\n"

    msg.attach(MIMEText(body, "plain"))

    with open(csv_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition",
                        f"attachment; filename={os.path.basename(csv_path)}")
        msg.attach(part)

    try:
        smtp_cfg = CFG.get("smtp_defaults", {})
        server = smtplib.SMTP(smtp_cfg.get("host", "smtp.gmail.com"),
                              smtp_cfg.get("port", 587))
        server.starttls()
        server.login(email_addr, email_pass)
        server.send_message(msg)
        server.quit()
        log(f"Email: Sent CSV to {email_addr}")
    except Exception as e:
        log(f"Email: Failed to send — {e}")

    return [], [(p, "manual upload required") for p in pins]


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    env = load_env()
    log("=== Pinterest Pin Uploader Started ===")
    send_telegram("📤 Job 3 started: Uploading pins to Pinterest", env)

    # Load pending pins
    pending = load_pending_pins()
    if not pending:
        log("No pending pins found. Exiting.")
        send_telegram("⚠️ Job 3: No pending pins to upload", env)
        return

    batch = pending[:UPLOAD_BATCH_SIZE]
    log(f"Processing batch of {len(batch)} pins")

    # Try methods in order: API → Browser → Email
    method_used = None
    uploaded, failed = [], []

    # Method 1: Pinterest API
    result = upload_via_api(batch, env)
    if result is not None:
        method_used = "Pinterest API v5"
        uploaded, failed = result
    else:
        # Method 2: Selenium
        result = upload_via_browser(batch, env)
        if result is not None:
            method_used = "Selenium browser"
            uploaded, failed = result
        else:
            # Method 3: Email CSV
            method_used = "Email CSV (manual upload)"
            uploaded, failed = upload_via_email(batch, env)

    # Summary
    failed_pins = [f[0] if isinstance(f, tuple) else f for f in failed]
    log(f"Method: {method_used}")
    log(f"Uploaded: {len(uploaded)} | Failed/Manual: {len(failed)}")

    summary = f"📤 Job 3 complete — {method_used}\n"
    summary += f"✅ Uploaded: {len(uploaded)}\n"
    if failed:
        summary += f"❌ Failed/Manual: {len(failed)}\n"
    if uploaded:
        summary += "\nUploaded pins:\n"
        for pin in uploaded[:10]:
            summary += f"  • {pin.get('product_name', '?')}\n"
        if len(uploaded) > 10:
            summary += f"  ... and {len(uploaded) - 10} more\n"

    send_telegram(summary, env)
    print(summary)
    log("=== Pinterest Pin Uploader Completed ===")


if __name__ == "__main__":
    main()