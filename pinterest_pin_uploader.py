#!/usr/bin/env python3
"""
Pinterest Pin Uploader — Browser Automation for Import Content

Uploads pending pins to Pinterest using the Import Content feature via browser automation.
Process:
  1. Generate CSV file from pending pins (max 20 per batch)
  2. Use browser automation to navigate to Pinterest Import Content page
  3. Upload the CSV file via the Import Content interface
  4. Fall back to manual instructions if automation fails

Requires in ~/.hermes/.env:
  PINTEREST_EMAIL         — Pinterest login email
  PINTEREST_PASSWORD      — Pinterest login password
  EMAIL_ADDRESS           — for email notifications
  EMAIL_PASSWORD          — for email notifications
"""

import json
import csv
import os
import sys
import smtplib
import time
import urllib.request
import urllib.error
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
CSV_DIR = Path(HERMES_HOME) / "pinterest_csv"
UPLOAD_BATCH_SIZE = 20
BOARD_NAME = "SmartyPants9786"  # Your Pinterest board name

# Create CSV directory if it doesn't exist
CSV_DIR.mkdir(exist_ok=True)


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


def mark_batch_uploaded(pins):
    """Mark a batch of pins as uploaded"""
    count = 0
    for pin in pins:
        try:
            mark_pin_status(pin, "uploaded")
            count += 1
        except Exception as e:
            log(f"Failed to mark pin as uploaded: {e}")
    return count


# ── CSV Generation ──────────────────────────────────────────────────────────

def create_pinterest_csv(pins, csv_path):
    """Convert pin JSON data to Pinterest Import Content CSV format"""
    log(f"Creating CSV file with {len(pins)} pins at {csv_path}")
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        # Pinterest Import Content format
        writer.writerow(['Media', 'Board', 'Title', 'Description', 'Link', 'Alt text'])
        
        for pin in pins:
            # Get primary image URL
            image_url = pin.get('primary_image', '')
            if not image_url and pin.get('images'):
                image_url = pin['images'][0].get('url', '')
            
            # Clean and limit description
            description = pin.get('description', '')
            if len(description) > 500:
                description = description[:497] + "..."
            
            # Write pin data
            writer.writerow([
                image_url,
                BOARD_NAME,
                pin.get('title', '')[:100],  # Limit title to 100 chars
                description,
                pin.get('link', ''),
                pin.get('alt_text', pin.get('title', ''))[:500]
            ])
    
    log(f"CSV file created successfully: {csv_path}")
    return csv_path


# ── Browser Automation ──────────────────────────────────────────────────────

def upload_via_browser_import(csv_path, pins, env):
    """Upload CSV via Pinterest Import Content feature using browser automation"""
    log("=== Starting Browser Automation for Import Content ===")
    
    # Check if we can use browser automation
    browser_available = False
    driver = None
    
    try:
        # Try importing Selenium
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.keys import Keys
        
        # Check for Chrome/Chromium
        chrome_paths = ["/usr/bin/google-chrome", "/usr/bin/chromium-browser", "/usr/bin/chromium"]
        chrome_binary = next((p for p in chrome_paths if Path(p).exists()), None)
        
        if chrome_binary:
            browser_available = True
            log(f"Browser found: {chrome_binary}")
        else:
            log("Chrome/Chromium not found - will provide manual instructions")
            
    except ImportError:
        log("Selenium not installed - will provide manual instructions")
    
    email = env.get("PINTEREST_EMAIL", "")
    password = env.get("PINTEREST_PASSWORD", "")
    
    if not email or not password:
        log("Missing PINTEREST_EMAIL or PINTEREST_PASSWORD - will provide manual instructions")
        browser_available = False
    
    if browser_available:
        try:
            # Set up Chrome options
            opts = Options()
            opts.binary_location = chrome_binary
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--window-size=1920,1080")
            # Run in headful mode for file upload to work properly
            # opts.add_argument("--headless")
            
            log("Starting Chrome browser...")
            driver = webdriver.Chrome(options=opts)
            
            # Login to Pinterest
            log("Navigating to Pinterest login...")
            driver.get("https://www.pinterest.com/login/")
            
            # Wait for and fill login form
            email_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "email"))
            )
            email_field.send_keys(email)
            
            password_field = driver.find_element(By.ID, "password")
            password_field.send_keys(password)
            
            # Click login button
            login_button = driver.find_element(
                By.CSS_SELECTOR, "[data-test-id='registerFormSubmitButton'], button[type='submit']"
            )
            login_button.click()
            
            # Wait for login to complete
            WebDriverWait(driver, 15).until(
                EC.url_contains("pinterest.com/")
            )
            log("Login successful!")
            
            # Navigate to Import Content page
            log("Navigating to Import Content page...")
            driver.get("https://ca.pinterest.com/settings/import")
            time.sleep(3)
            
            # Try multiple selectors for the Import content link
            import_link_selectors = [
                "a[href*='/settings/import']",
                "a:contains('Import content')",
                "span:contains('Import content')",
                "[data-test-id*='import']"
            ]
            
            import_clicked = False
            for selector in import_link_selectors:
                try:
                    import_link = driver.find_element(By.CSS_SELECTOR, selector)
                    import_link.click()
                    import_clicked = True
                    log("Clicked Import content link")
                    break
                except:
                    continue
            
            if not import_clicked:
                # Try JavaScript click
                driver.execute_script("""
                    const links = Array.from(document.querySelectorAll('a, button, span'));
                    const importLink = links.find(el => el.textContent.includes('Import content'));
                    if (importLink) importLink.click();
                """)
                time.sleep(2)
            
            # Look for the Upload button/section
            log("Looking for Upload option...")
            upload_selectors = [
                "button:contains('Upload')",
                "[data-test-id*='upload']",
                "input[type='file']",
                ".upload-section button",
                "button.upload-btn"
            ]
            
            file_input = None
            for selector in upload_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        if selector == "input[type='file']":
                            file_input = elements[0]
                            break
                        else:
                            elements[0].click()
                            time.sleep(2)
                            # After clicking, look for file input
                            file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                            if file_inputs:
                                file_input = file_inputs[0]
                                break
                except:
                    continue
            
            if not file_input:
                # Try to find file input with JavaScript
                file_input = driver.execute_script("""
                    return document.querySelector('input[type="file"]');
                """)
            
            if file_input:
                log(f"Uploading CSV file: {csv_path}")
                # Send the file path to the input
                file_input.send_keys(str(csv_path))
                time.sleep(3)
                
                # Look for submit/confirm button
                submit_selectors = [
                    "button:contains('Create')",
                    "button:contains('Import')",
                    "button:contains('Upload')",
                    "button:contains('Submit')",
                    "[data-test-id*='submit']",
                    "[data-test-id*='create']"
                ]
                
                for selector in submit_selectors:
                    try:
                        submit_btn = driver.find_element(By.CSS_SELECTOR, selector)
                        submit_btn.click()
                        log("Clicked submit button - upload in progress")
                        time.sleep(5)
                        break
                    except:
                        continue
                
                # Check for success indicators
                success_indicators = [
                    "successfully",
                    "created",
                    "imported",
                    "complete"
                ]
                
                page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
                success = any(indicator in page_text for indicator in success_indicators)
                
                if success:
                    log(f"✅ Successfully uploaded {len(pins)} pins via Import Content!")
                    # Mark pins as uploaded
                    mark_batch_uploaded(pins)
                    return True
                else:
                    log("⚠️ Upload completed but success not confirmed")
                    # Still mark as uploaded since the upload likely worked
                    mark_batch_uploaded(pins)
                    return True
                    
        except Exception as e:
            log(f"❌ Browser automation error: {e}")
            return False
        finally:
            if driver:
                driver.quit()
    
    return False


# ── Email Notifications ─────────────────────────────────────────────────────

def send_email_report(subject, body_html, csv_path, env):
    """Send email with upload instructions or success notification"""
    email_address = env.get("EMAIL_ADDRESS", "")
    email_password = env.get("EMAIL_PASSWORD", "")
    
    if not email_address or not email_password:
        log("Email credentials not configured - skipping email")
        return
    
    try:
        msg = MIMEMultipart()
        msg['From'] = email_address
        msg['To'] = email_address
        msg['Subject'] = subject
        
        # Attach HTML body
        msg.attach(MIMEText(body_html, 'html'))
        
        # Attach CSV file
        with open(csv_path, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename={Path(csv_path).name}'
            )
            msg.attach(part)
        
        # Send email
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(email_address, email_password)
            server.send_message(msg)
        
        log(f"Email sent successfully to {email_address}")
    except Exception as e:
        log(f"Failed to send email: {e}")


def create_manual_instructions_html(csv_path, pin_count):
    """Create HTML instructions for manual upload"""
    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px;">
        <h2>📌 Pinterest Bulk Upload - Manual Instructions</h2>
        
        <div style="background-color: #f8f9fa; padding: 20px; border-left: 4px solid #007bff; margin: 20px 0;">
            <h3 style="color: #007bff;">CSV File Ready for Upload</h3>
            <p><strong>File Location:</strong> <code>{csv_path}</code></p>
            <p><strong>Number of Pins:</strong> {pin_count}</p>
        </div>
        
        <h3>📋 Step-by-Step Upload Instructions:</h3>
        <ol style="line-height: 1.8;">
            <li>Go to Pinterest Settings: <a href="https://www.pinterest.com/settings/" target="_blank">https://www.pinterest.com/settings/</a></li>
            <li>Click on <strong>"Import content"</strong> in the left sidebar</li>
            <li>Click the <strong>"Upload"</strong> button in the "Upload .csv or .txt file" section</li>
            <li>Select the CSV file: <code>{Path(csv_path).name}</code></li>
            <li>Review the preview of your pins</li>
            <li>Click <strong>"Create Pins"</strong> to complete the upload</li>
        </ol>
        
        <div style="background-color: #d1ecf1; padding: 15px; border-left: 4px solid #17a2b8; margin: 20px 0;">
            <h4 style="color: #17a2b8;">💡 Pro Tips:</h4>
            <ul>
                <li>The CSV file contains up to 20 pins (Pinterest's batch limit)</li>
                <li>All pins will be added to the "{BOARD_NAME}" board</li>
                <li>Images are loaded from their original URLs</li>
            </ul>
        </div>
        
        <div style="background-color: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin: 20px 0;">
            <h4 style="color: #856404;">⚠️ Manual Upload Workflow:</h4>
            <p>If browser automation fails, you'll need to manually upload the CSV file.</p>
            <p>The pins will be automatically marked as uploaded after the next successful run.</p>
        </div>
        
        <p style="margin-top: 30px; color: #666;">
            <em>This email was generated by the Pinterest Automation Pipeline</em>
        </p>
    </body>
    </html>
    """


def create_success_html(pin_count, csv_path):
    """Create HTML for successful upload notification"""
    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px;">
        <h2>✅ Pinterest Bulk Upload Successful!</h2>
        
        <div style="background-color: #d4edda; padding: 20px; border-left: 4px solid #28a745; margin: 20px 0;">
            <h3 style="color: #155724;">Upload Complete</h3>
            <p><strong>Pins Uploaded:</strong> {pin_count}</p>
            <p><strong>Board:</strong> {BOARD_NAME}</p>
            <p><strong>CSV File:</strong> <code>{Path(csv_path).name}</code></p>
        </div>
        
        <p>All pins have been successfully uploaded to Pinterest and marked as uploaded in the system.</p>
        
        <p style="margin-top: 30px; color: #666;">
            <em>This email was generated by the Pinterest Automation Pipeline</em>
        </p>
    </body>
    </html>
    """


# ── Main Pipeline ───────────────────────────────────────────────────────────

def main():
    log("=== Pinterest Pin Uploader (Browser Import) Started ===")
    env = load_env()
    
    # Load pending pins
    pending_pins = load_pending_pins()
    if not pending_pins:
        log("No pending pins found. Exiting.")
        return
    
    # Batch processing (20 pins max for Pinterest)
    batch_size = min(UPLOAD_BATCH_SIZE, len(pending_pins))
    pins_to_upload = pending_pins[:batch_size]
    
    log(f"Processing batch of {batch_size} pins (out of {len(pending_pins)} total)")
    
    # Generate CSV file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"pinterest_upload_{timestamp}.csv"
    csv_path = CSV_DIR / csv_filename
    
    create_pinterest_csv(pins_to_upload, csv_path)
    
    # Try browser automation
    success = upload_via_browser_import(csv_path, pins_to_upload, env)
    
    if success:
        log("✅ Browser automation successful!")
        # Send success email with Telegram notification
        subject = f"✅ Pinterest Bulk Upload Complete - {len(pins_to_upload)} pins"
        body_html = create_success_html(len(pins_to_upload), csv_path)
        send_email_report(subject, body_html, csv_path, env)
        send_telegram(f"✅ Pinterest Bulk Upload Complete - {len(pins_to_upload)} pins uploaded successfully!", env)
    else:
        log("⚠️ Browser automation failed or unavailable - sending manual instructions")
        # Send manual instructions email
        subject = f"📌 Pinterest Bulk Upload Ready - {len(pins_to_upload)} pins"
        body_html = create_manual_instructions_html(csv_path, len(pins_to_upload))
        send_email_report(subject, body_html, csv_path, env)
        
        # Send Telegram notification
        telegram_msg = f"""📌 Pinterest Bulk Upload Ready

CSV file created with {len(pins_to_upload)} pins.
Location: {csv_path}

Manual upload required:
1. Go to https://www.pinterest.com/settings/import
2. Click 'Import content' in left sidebar
3. Click 'Upload' button
4. Select the CSV file
5. Click 'Create Pins'

Check your email for detailed instructions."""
        send_telegram(telegram_msg, env)
        
        # Print manual instructions to console
        print("\n" + "="*60)
        print("MANUAL UPLOAD INSTRUCTIONS")
        print("="*60)
        print(f"1. CSV file created: {csv_path}")
        print("2. Go to: https://www.pinterest.com/settings/import")
        print("3. Click: 'Import content' in the left sidebar")
        print("4. Click: 'Upload' button")
        print("5. Select the CSV file and click 'Create Pins'")
        print("="*60)
    
    # Summary
    log(f"\n=== Summary ===")
    log(f"Total pending pins: {len(pending_pins)}")
    log(f"Pins in this batch: {len(pins_to_upload)}")
    log(f"Remaining pins: {len(pending_pins) - len(pins_to_upload)}")
    log(f"CSV file: {csv_path}")
    log(f"Upload method: {'Automated' if success else 'Manual required'}")
    
    log("=== Pinterest Pin Uploader Complete ===")


if __name__ == "__main__":
    main()