#!/usr/bin/env python3
"""
Pinterest Pin Generator — Email-Based Report

Reads the latest trending tech products CSV, generates Pinterest pin data,
and emails a comprehensive summary with all pin details.

No Google Drive dependency - pure local processing with email delivery.
Output: Plain text summary to stdout + detailed email report.
Cost: $0 per run.
"""

import os
import sys
import csv
import json
import smtplib
import subprocess
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline_paths as paths
import pipeline_manifest as manifest

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
BOARD_NAME = CFG.get("pinterest", {}).get("board_name", "SmartyPants2786")
MIN_PINS_GATE = CFG.get("quality_gates", {}).get("min_pins", 3)

HASHTAGS = {
    "Smart Home and IoT": "#SmartHome #IoT #HomeAutomation #TechHome #GadgetGoals",
    "Phone and Tablet Accessories": "#PhoneTech #MobileGadgets #SmartphoneAccessories #TechAccessories",
    "Audio and Wearables": "#AudioTech #Wearables #Earbuds #SmartWatch #TechWearables",
    "Cool Gadgets and Gizmos": "#CoolGadgets #TechGadgets #GadgetLover #Innovation #MustHave",
    "PC and Gaming Tech": "#GamingTech #PCGaming #GamingSetup #TechDeals #PCBuild",
}


# ── Email Functions ──────────────────────────────────────────────────────────

def _load_env_var(name):
    """Load environment variable from .env file"""
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


def send_email_report(subject, body_text, pins_data, errors, csv_attachment_path=None, pins_location=None):
    """Send detailed email report with pin summaries"""
    email_address = _load_env_var("EMAIL_ADDRESS")
    email_password = _load_env_var("EMAIL_PASSWORD")
    
    if not email_address or not email_password:
        print("WARNING: Email credentials not found in .env file")
        return False
    
    # Create email message
    msg = MIMEMultipart()
    msg['From'] = email_address
    msg['To'] = email_address
    msg['Subject'] = subject
    
    # Create HTML body with pin details
    html_body = f"""
    <html>
    <head></head>
    <body>
        <h2>Pinterest Pin Generator Report</h2>
        <p><strong>Date:</strong> {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
        
        <h3>📊 Summary</h3>
        <ul>
            <li><strong>Total Pins Created:</strong> {len(pins_data)}</li>
            <li><strong>Errors:</strong> {len(errors)}</li>
            <li><strong>Board:</strong> {BOARD_NAME}</li>
        </ul>
        
        <h3>📌 Pin Details</h3>
    """
    
    for i, pin in enumerate(pins_data, 1):
        procured_status = "✓ ALREADY PROCURED" if pin.get("procured", False) else "🆕 NEW PRODUCT"
        
        html_body += f"""
        <div style="border: 1px solid #ddd; margin: 10px 0; padding: 15px; border-radius: 8px;">
            <h4>Pin #{i}: {pin['product_name']} {procured_status}</h4>
            <p><strong>Title:</strong> {pin['title']}</p>
            <p><strong>Category:</strong> {pin['category']}</p>
            <p><strong>Price Range:</strong> {pin['price_range']}</p>
            <p><strong>Description:</strong> {pin['description']}</p>
            <p><strong>Amazon Link:</strong> <a href="{pin['link']}">{pin['link']}</a></p>
            <p><strong>Images:</strong></p>
            <ul>
        """
        
        for img in pin.get('images', []):
            html_body += f'<li><a href="{img["url"]}">{img["url"]}</a></li>'
        
        html_body += """
            </ul>
            <p><strong>Alt Text:</strong> {}</p>
        </div>
        """.format(pin['alt_text'])
    
    if errors:
        html_body += """
        <h3>❌ Errors</h3>
        <ul>
        """
        for product_name, error_msg in errors:
            html_body += f"<li><strong>{product_name}:</strong> {error_msg}</li>"
        html_body += "</ul>"
    
    html_body += """
        <h3>📁 Local Storage</h3>
        <p>Pin JSON files saved to: <code>{}</code></p>

        <hr>
        <p><em>This report was generated automatically by the Pinterest Pin Generator script.</em></p>
    </body>
    </html>
    """.format(pins_location or "(run directory)")
    
    # Attach both plain text and HTML versions
    msg.attach(MIMEText(body_text, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    # Attach bulk upload CSV if provided
    if csv_attachment_path and os.path.exists(csv_attachment_path):
        with open(csv_attachment_path, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition',
                            f'attachment; filename={os.path.basename(csv_attachment_path)}')
            msg.attach(part)

    # Send email
    try:
        smtp_config = CFG.get("smtp_defaults", {})
        server = smtplib.SMTP(smtp_config.get("host", "smtp.gmail.com"), 
                            smtp_config.get("port", 587))
        server.starttls()
        server.login(email_address, email_password)
        
        text = msg.as_string()
        server.sendmail(email_address, email_address, text)
        server.quit()
        
        print(f"✅ Email sent successfully to {email_address}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False


# ── CSV Processing ──────────────────────────────────────────────────────────

def load_csv_data(csv_path):
    """Load and parse the trending tech products CSV from the run directory."""
    if not os.path.exists(csv_path):
        print(f"ERROR: CSV file not found at {csv_path}")
        return []

    products = []
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
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
                    "procured": row.get("Procured", "").strip().lower() in ['yes', 'true', '1', 'already procured']
                })
        
        print(f"✅ Loaded {len(products)} products from CSV")
        return products
        
    except Exception as e:
        print(f"ERROR: Failed to read CSV: {e}")
        return []


# ── Image Fetching ──────────────────────────────────────────────────────────

def fetch_amazon_product_images(product_name, amazon_link, num_images=2):
    """Fetch product images from Amazon link.
    
    Falls back to search if direct link doesn't return images.
    """
    import urllib.request
    import re
    
    images = []
    
    # Try direct product page first
    if amazon_link and "/dp/" in amazon_link:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            req = urllib.request.Request(amazon_link, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
                
                # Extract image URLs from various patterns
                patterns = [
                    r'"imageGalleryData":\s*\[?\s*\{"initial":\s*"([^"]+)"',
                    r'"landingImage":\s*"([^"]+)"',
                    r'"hiRes":\s*"([^"]+)"',
                    r'data-a-dynamic-image=\'([^\']+)\'',
                    r'src="(https://m\.media-amazon\.com/images/I/[^"]+)"',
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, html)
                    for match in matches:
                        url = match if isinstance(match, str) else match[0]
                        if url.startswith('http') and '/images/I/' in url:
                            images.append(url)
                            if len(images) >= num_images:
                                return images
        except Exception:
            pass
    
    # Fallback: search Amazon for product images
    if len(images) < num_images:
        try:
            import urllib.parse
            query = urllib.parse.quote_plus(product_name)
            search_url = f"https://www.amazon.com/s?k={query}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            req = urllib.request.Request(search_url, headers=headers)
            
            with urllib.request.urlopen(req, timeout=5) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
                
                # Extract image URLs from search results
                pattern = r'src="(https://m\.media-amazon\.com/images/I/[^"\.]+\._[^"]*\.jpg)"'
                matches = re.findall(pattern, html)
                
                for match in matches:
                    if match not in images:
                        images.append(match)
                        if len(images) >= num_images:
                            break
        except Exception:
            pass
    
    return images[:num_images]


# ── Pin Creation ────────────────────────────────────────────────────────────

def create_pin_json(product, date_str):
    """Generate Pinterest pin JSON data for a product"""
    name = product["name"]
    category = product["category"]
    price = product["price_range"]
    description = product["description"]
    caption = product["pin_caption"]
    link = product["amazon_link"]
    image_1 = product["image_1"]
    image_2 = product["image_2"]
    procured = product.get("procured", False)

    # Fetch images if not provided by Job 1
    if not image_1 and not image_2:
        fetched_imgs = fetch_amazon_product_images(name, link, num_images=2)
        if fetched_imgs:
            image_1 = fetched_imgs[0] if len(fetched_imgs) > 0 else ""
            image_2 = fetched_imgs[1] if len(fetched_imgs) > 1 else ""

    AFFILIATE_DISCLOSURE = "\n\n#affiliate #ad  (This pin contains affiliate links — I earn a commission if you purchase through my link)"
    category_tags = HASHTAGS.get(category, "#TechGadgets #Innovation")
    pin_description = caption if caption else f"{name} - {description}"
    if category_tags not in pin_description:
        pin_description = f"{pin_description} {category_tags}"
    # Truncate description to leave room for affiliate disclosure within 500 chars
    max_desc_len = 500 - len(AFFILIATE_DISCLOSURE)
    if len(pin_description) > max_desc_len:
        pin_description = pin_description[:max_desc_len - 3] + "..."
    pin_description = f"{pin_description}{AFFILIATE_DISCLOSURE}"
    
    title = f"{name} - {price}" if price else name
    title = title[:100]

    images = []
    if image_1:
        images.append({"url": image_1, "size": "large"})
    if image_2:
        images.append({"url": image_2, "size": "large"})

    return {
        "product_name": name,
        "board": BOARD_NAME.lower(),
        "title": title,
        "description": pin_description,
        "link": link,
        "category": category,
        "alt_text": f"Product image of {name} - {description[:100]}",
        "images": images,
        "primary_image": image_1 or image_2 or "",
        "price_range": price,
        "procured": procured,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready_for_upload",
    }


# ── Pinterest Bulk Upload CSV ───────────────────────────────────────────────

def generate_pinterest_csv(pins_data, run_dir):
    """Write the Pinterest bulk-upload CSV into the run directory.

    Returns (csv_path, valid_pins, excluded_pins). The run dir is itself the
    archive — there is no separate archive copy.
    """
    csv_path = run_dir / paths.BULK_CSV_NAME

    valid_pins = 0
    excluded_pins = 0
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Title", "Media URL", "Pinterest board", "Description", "Link", "Keywords"])

        for pin in pins_data:
            image_url = pin.get("primary_image", "")
            if not image_url and pin.get("images"):
                image_url = pin["images"][0].get("url", "")

            if not image_url:
                excluded_pins += 1
                print(f"⚠️  Excluding pin '{pin.get('title', 'Unknown')}' - no media URL")
                continue

            description = pin.get("description", "")
            if len(description) > 500:
                description = description[:497] + "..."

            writer.writerow([
                pin.get('title', '')[:100],
                image_url,
                BOARD_NAME,
                description,
                pin.get('link', ''),
                pin.get('alt_text', pin.get('title', ''))[:500],
            ])
            valid_pins += 1

    print(f"📄 Pinterest bulk upload CSV created: {csv_path} ({valid_pins} valid pins, {excluded_pins} excluded due to missing media URL)")
    return str(csv_path), valid_pins, excluded_pins


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    today = datetime.now(timezone.utc)
    date_str = today.strftime("%Y%m%d")
    job2_start = time.time()

    print(f"📌 Pinterest Pin Generator started: {today.strftime('%Y-%m-%d %H:%M:%S')}")

    # Resolve the run dir set up by Job 1. If invoked standalone (no env and
    # no `current` symlink), refuse rather than guess — Job 1 owns run creation.
    run_dir = paths.resolve_run_dir()
    if run_dir is None:
        print("❌ No run directory resolved (HERMES_PIPELINE_RUN_ID unset and no `current` symlink).")
        print("   Run Job 1 (trending_tech_products.py) first, or set HERMES_PIPELINE_RUN_ID.")
        sys.exit(2)
    print(f"  Run id: {paths.run_id_of(run_dir)}")

    input_csv = run_dir / paths.RAW_CSV_NAME
    products = load_csv_data(str(input_csv))
    if not products:
        print(f"❌ No products found in {input_csv}")
        manifest.append_error(run_dir, "job2", f"input CSV missing/empty: {input_csv}")
        manifest.finalize(run_dir, "failed")
        sys.exit(2)

    pins_out_dir = paths.pins_dir(run_dir)
    pins_out_dir.mkdir(parents=True, exist_ok=True)

    # Create pin files
    created = []
    errors = []
    pins_data = []

    for product in products:
        if not product["name"]:  # Skip empty products
            continue

        num = product["number"].zfill(2) if product["number"] else str(len(created) + 1).zfill(2)
        filename = f"pin_{num}.json"
        filepath = pins_out_dir / filename

        try:
            pin_data = create_pin_json(product, date_str)

            # Save JSON file inside the run dir
            with open(filepath, "w", encoding='utf-8') as f:
                json.dump(pin_data, f, indent=2, ensure_ascii=False)

            created.append((filename, product["name"]))
            pins_data.append(pin_data)

        except Exception as e:
            errors.append((product["name"], str(e)))
    
    # Generate summary
    new_products = [p for p in pins_data if not p.get("procured", False)]
    procured_products = [p for p in pins_data if p.get("procured", False)]
    
    summary_text = f"""Pinterest Pin Generator Report - {today.strftime('%B %d, %Y')}

📊 SUMMARY:
• Total pins created: {len(pins_data)}
• New products: {len(new_products)}
• Already procured: {len(procured_products)}
• Errors: {len(errors)}
• Local storage: {pins_out_dir}

🆕 NEW PRODUCTS ({len(new_products)}):"""
    
    for pin in new_products[:10]:  # Show first 10 new products
        summary_text += f"\n  • {pin['product_name']} - {pin['price_range']} ({pin['category']})"
    
    if len(new_products) > 10:
        summary_text += f"\n  ... and {len(new_products) - 10} more new products"
    
    if procured_products:
        summary_text += f"\n\n✓ ALREADY PROCURED ({len(procured_products)}):"
        for pin in procured_products[:5]:  # Show first 5 procured products
            summary_text += f"\n  • {pin['product_name']} - {pin['price_range']}"
        if len(procured_products) > 5:
            summary_text += f"\n  ... and {len(procured_products) - 5} more procured products"
    
    if errors:
        summary_text += f"\n\n❌ ERRORS ({len(errors)}):"
        for product_name, error_msg in errors:
            summary_text += f"\n  • {product_name}: {error_msg}"
    
    # Generate Pinterest bulk upload CSV (into the run dir)
    csv_path = None
    valid_pins = 0
    excluded_pins = 0
    if pins_data:
        csv_path, valid_pins, excluded_pins = generate_pinterest_csv(pins_data, run_dir)
        summary_text += f"\n\n📄 Pinterest CSV: {csv_path}"

    manifest.set_stage(run_dir, "job2", {
        "pins_generated": valid_pins,
        "excluded_no_media": excluded_pins,
        "csv": csv_path,
        "min_pins_gate": MIN_PINS_GATE,
        "elapsed_s": round(time.time() - job2_start, 2),
    })

    # Health gate: refuse to chain Job 3 with too few pins. Historically the
    # uploader happily published 0–2-pin runs and the failure was invisible.
    if valid_pins < MIN_PINS_GATE:
        msg = f"min_pins gate failed: {valid_pins} < {MIN_PINS_GATE}"
        print(f"\n🚫 {msg} — refusing to chain Job 3")
        manifest.append_error(run_dir, "job2", msg)
        manifest.finalize(run_dir, "failed")
        # Still send the report email so a human sees the degradation.
        email_subject = f"⚠️ Pinterest Pin Generator: only {valid_pins} pins (gate {MIN_PINS_GATE})"
        send_email_report(email_subject, summary_text + f"\n\n🚫 {msg}", pins_data, errors,
                          csv_attachment_path=csv_path, pins_location=str(pins_out_dir))
        sys.exit(3)

    # Print summary to stdout
    print("\n" + summary_text)

    # Send detailed email report
    email_subject = f"Pinterest Pin Generator Report - {len(pins_data)} pins created ({len(new_products)} new)"
    email_success = send_email_report(email_subject, summary_text, pins_data, errors,
                                      csv_attachment_path=csv_path, pins_location=str(pins_out_dir))

    if email_success:
        print(f"\n✅ Report complete: {len(pins_data)} pins created, detailed email sent")
    else:
        print(f"\n⚠️ Report complete: {len(pins_data)} pins created, but email failed")

    # Chain Job 3 (Pinterest Pin Uploader) immediately after Job 2 completes.
    # Pass the run id so Job 3 reads from the same per-run directory.
    if pins_data:
        try:
            print("\n🔗 Chaining Job 3 (Pinterest Pin Uploader)...")
            script_dir = os.path.dirname(os.path.abspath(__file__))
            uploader_script = os.path.join(script_dir, "pinterest_pin_uploader.py")
            job3_env = os.environ.copy()
            job3_env[paths.RUN_ID_ENV] = paths.run_id_of(run_dir)
            result = subprocess.run(
                [sys.executable, uploader_script],
                capture_output=True, text=True, timeout=300,
                env=job3_env,
                cwd=script_dir,
            )

            if result.stdout:
                print("--- JOB 3 STDOUT ---")
                print(result.stdout.rstrip())
            if result.stderr:
                print("--- JOB 3 STDERR ---")
                print(result.stderr.rstrip())

            if result.returncode == 0:
                print("\n✅ Job 3 chained successfully: Pinterest pins uploaded")
            else:
                tail = (result.stderr or result.stdout or "Unknown error")[-400:]
                print(f"\n⚠️ Job 3 exit code {result.returncode}: {tail}")

        except subprocess.TimeoutExpired:
            print(f"\n⏰ Job 3 chaining timed out after 300 seconds")
        except Exception as e:
            print(f"\n⚠️ Job 3 chaining error: {str(e)[:200]}")
    else:
        print("\n⊘ Skipping Job 3 chaining: No pins to upload")


if __name__ == "__main__":
    main()