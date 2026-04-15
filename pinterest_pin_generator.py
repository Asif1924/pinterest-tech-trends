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
from pathlib import Path
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

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
BOARD_NAME = CFG.get("pinterest", {}).get("board_name", "SmartyPants9786")
CSV_PATH = CFG.get("csv_path", "/tmp/trending_tech_products.csv")

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


def send_email_report(subject, body_text, pins_data, errors):
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
    """.format(PINS_DIR)
    
    # Attach both plain text and HTML versions
    msg.attach(MIMEText(body_text, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))
    
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

def load_csv_data():
    """Load and parse the trending tech products CSV"""
    if not os.path.exists(CSV_PATH):
        print(f"ERROR: CSV file not found at {CSV_PATH}")
        return []
    
    products = []
    try:
        with open(CSV_PATH, 'r', encoding='utf-8') as f:
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


def cleanup_old_pins_local():
    """Clean up old pin files from local directory"""
    os.makedirs(PINS_DIR, exist_ok=True)
    
    deleted = 0
    try:
        for file_path in Path(PINS_DIR).glob("*.json"):
            file_path.unlink()
            deleted += 1
    except Exception as e:
        print(f"Warning: Could not clean old pins: {e}")
    
    return deleted


# ── Pinterest Bulk Upload CSV ───────────────────────────────────────────────

def generate_pinterest_csv(pins_data, date_str):
    """Generate a Pinterest-compatible CSV for bulk upload.
    Pinterest Import Content format: Media, Board, Title, Description, Link, Alt text
    """
    csv_path = os.path.join(HERMES_HOME, f"pinterest_bulk_upload_{date_str}.csv")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Media", "Board", "Title", "Description", "Link", "Alt text"])

        for pin in pins_data:
            image_url = pin.get("primary_image", "")
            if not image_url and pin.get("images"):
                image_url = pin["images"][0].get("url", "")

            description = pin.get("description", "")
            if len(description) > 500:
                description = description[:497] + "..."

            writer.writerow([
                image_url,
                pin.get("board", BOARD_NAME.lower()),
                pin.get("title", ""),
                description,
                pin.get("link", ""),
                pin.get("alt_text", ""),
            ])

    print(f"📄 Pinterest bulk upload CSV created: {csv_path} ({len(pins_data)} pins)")
    return csv_path


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    today = datetime.now(timezone.utc)
    date_str = today.strftime("%Y%m%d")
    
    print(f"📌 Pinterest Pin Generator started: {today.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load product data from CSV
    products = load_csv_data()
    if not products:
        print("❌ No products found or CSV loading failed")
        return
    
    # Clean up old pin files
    deleted_count = cleanup_old_pins_local()
    print(f"🗑️ Cleaned up {deleted_count} old pin files")
    
    # Create pin files
    created = []
    errors = []
    pins_data = []
    
    for product in products:
        if not product["name"]:  # Skip empty products
            continue
            
        num = product["number"].zfill(2) if product["number"] else str(len(created) + 1).zfill(2)
        filename = f"pin_{date_str}_{num}.json"
        filepath = os.path.join(PINS_DIR, filename)
        
        try:
            pin_data = create_pin_json(product, date_str)
            
            # Save JSON file locally
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
• Local storage: {PINS_DIR}

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
    
    # Generate Pinterest bulk upload CSV
    csv_path = None
    if pins_data:
        csv_path = generate_pinterest_csv(pins_data, date_str)
        summary_text += f"\n\n📄 Pinterest CSV: {csv_path}"

    # Print summary to stdout
    print("\n" + summary_text)

    # Send detailed email report
    email_subject = f"Pinterest Pin Generator Report - {len(pins_data)} pins created ({len(new_products)} new)"
    email_success = send_email_report(email_subject, summary_text, pins_data, errors)
    
    if email_success:
        print(f"\n✅ Report complete: {len(pins_data)} pins created, detailed email sent")
    else:
        print(f"\n⚠️ Report complete: {len(pins_data)} pins created, but email failed")


if __name__ == "__main__":
    main()