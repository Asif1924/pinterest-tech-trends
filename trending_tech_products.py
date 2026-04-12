#!/usr/bin/env python3
"""
Trending Tech Products — FULLY AUTOMATED (no AI needed)

Complete pipeline in one script:
  1. Scrapes 6 sources for trending tech products
  2. Curates top 20 by Reddit score + source count
  3. Fetches 2 Amazon product images per product
  4. Generates CSV with all data
  5. Uploads CSV to Google Drive
  6. Emails CSV to inbox
  7. Sends formatted Telegram report

Output: Plain text Telegram report to stdout.
Cost: $0 per run.
"""

import os
import sys
import csv
import io
import json
import re
import time
import smtplib
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from html.parser import HTMLParser
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# ── Config ──────────────────────────────────────────────────────────────────
HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
AFFILIATE_TAG = "allitechstore-20"
DRIVE_FOLDER_ID = "1w-XAxZccQ4wk4NOKwm2YDusouLvO-a6L"  # PinterestAutomation
CSV_PATH = "/tmp/trending_tech_products.csv"
TOP_N = 20

CATEGORIES = [
    "Smart Home and IoT",
    "Phone and Tablet Accessories",
    "Audio and Wearables",
    "Cool Gadgets and Gizmos",
    "PC and Gaming Tech",
]

# Keywords for auto-categorization
CATEGORY_KEYWORDS = {
    "Smart Home and IoT": ["smart home", "iot", "robot vacuum", "doorbell", "thermostat",
        "smart light", "led strip", "curtain", "smart plug", "alexa", "matter",
        "smart speaker", "air purifier", "smart fridge", "ecovacs", "switchbot",
        "nanoleaf", "govee", "ring", "nest", "air fryer"],
    "Phone and Tablet Accessories": ["phone", "iphone", "galaxy", "pixel", "fold",
        "foldable", "tablet", "ipad", "case", "charger", "power bank", "cable",
        "magsafe", "qi", "kindle", "e-ink", "smartphone", "xiaomi", "oneplus"],
    "Audio and Wearables": ["earbuds", "headphones", "headset", "speaker", "audio",
        "airpods", "bose", "jbl", "sony wh", "watch", "ring", "wearable", "fitbit",
        "oura", "garmin", "glasses", "smart glasses", "ray-ban", "shokz", "soundcore"],
    "Cool Gadgets and Gizmos": ["gadget", "fan", "projector", "camera", "drone",
        "3d print", "laser", "mug", "ember", "airtag", "tracker", "vr", "ar",
        "instax", "gopro", "dji", "dyson", "portable", "handheld"],
    "PC and Gaming Tech": ["laptop", "pc", "gaming", "keyboard", "mouse", "monitor",
        "gpu", "ram", "ddr5", "ssd", "controller", "console", "steam", "nintendo",
        "handheld gaming", "backbone", "keychron", "razer", "corsair", "asus",
        "dell xps", "macbook", "lenovo", "msi", "benq", "screenbar"],
}

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def load_env():
    """Read all env vars from ~/.hermes/.env."""
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


def send_telegram(text, env=None):
    """Send a Telegram message."""
    if env is None:
        env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_HOME_CHANNEL", "")
    if not token or not chat_id:
        return
    try:
        data = json.dumps({"chat_id": chat_id, "text": text}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self._skip = False
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip = True
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = False
    def handle_data(self, data):
        if not self._skip:
            self.text_parts.append(data)
    def get_text(self):
        return " ".join(self.text_parts)


def fetch_url(url, timeout=15):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/json",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"ERROR: {e}"


def html_to_text(html):
    parser = TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.get_text()


def make_affiliate_link(product_name):
    terms = urllib.parse.quote_plus(product_name)
    return f"https://www.amazon.com/s?k={terms}&tag={AFFILIATE_TAG}"


# ── Scrapers ────────────────────────────────────────────────────────────────

BRANDS = [
    "Apple", "Samsung", "Google", "Sony", "Bose", "Anker", "Logitech",
    "Razer", "JBL", "Meta", "Amazon", "Ring", "Nanoleaf", "Govee",
    "Dyson", "Ember", "Keychron", "BenQ", "XREAL", "Oura", "Backbone",
    "SwitchBot", "Dreame", "Roborock", "ecobee", "Philips", "TP-Link",
    "Eufy", "DJI", "GoPro", "Kindle", "Nintendo", "Valve", "Steam",
    "Lenovo", "ASUS", "MSI", "Corsair", "SteelSeries", "HyperX",
    "Nothing", "OnePlus", "Xiaomi", "Shokz", "Garmin", "Fitbit",
    "Dell", "HP", "LG", "TCL", "Roku", "Sonos", "Marshall",
]


def extract_products_from_text(text, source_name):
    products = []
    brand_pattern = "|".join(re.escape(b) for b in BRANDS)
    for line in text.split("\n"):
        line = line.strip()
        if not line or len(line) < 10 or len(line) > 300:
            continue
        if re.search(brand_pattern, line, re.IGNORECASE):
            if any(skip in line.lower() for skip in [
                "cookie", "privacy", "sign in", "subscribe", "copyright",
                "terms of", "about us", "contact", "navigation", "menu",
                "advertisement", "sponsored",
            ]):
                continue
            products.append({"raw_text": line[:250], "source": source_name, "score": 0})
    return products[:30]


def scrape_reddit_gadgets():
    products = []
    for sub in ["gadgets", "technology", "tech"]:
        url = f"https://www.reddit.com/r/{sub}/hot.json?limit=25"
        data = fetch_url(url)
        if data.startswith("ERROR"):
            continue
        try:
            parsed = json.loads(data)
            for child in parsed.get("data", {}).get("children", []):
                post = child.get("data", {})
                title = post.get("title", "")
                score = post.get("score", 0)
                if score > 50 and len(title) > 15:
                    products.append({
                        "raw_text": title,
                        "source": f"reddit/r/{sub}",
                        "score": score,
                        "url": post.get("url", ""),
                    })
        except (json.JSONDecodeError, KeyError):
            continue
        time.sleep(1)
    return products


def scrape_amazon_trending():
    products = []
    urls = [
        "https://www.amazon.com/gp/moversandshakers/electronics/",
        "https://www.amazon.com/Best-Sellers-Electronics/zgbs/electronics/",
    ]
    for url in urls:
        html = fetch_url(url)
        if html.startswith("ERROR"):
            continue
        text = html_to_text(html)
        products.extend(extract_products_from_text(text, "amazon"))
        time.sleep(1)
    return products


def scrape_google_trending_tech():
    queries = [
        "trending tech products this week 2026",
        "best selling gadgets Amazon electronics 2026",
    ]
    products = []
    for query in queries:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.google.com/search?q={encoded}&num=15"
        html = fetch_url(url)
        if html.startswith("ERROR"):
            continue
        text = html_to_text(html)
        products.extend(extract_products_from_text(text, f"google:{query[:30]}"))
        time.sleep(2)
    return products


def scrape_techradar():
    html = fetch_url("https://www.techradar.com/best/best-gadgets")
    if html.startswith("ERROR"):
        return []
    return extract_products_from_text(html_to_text(html), "techradar")


def scrape_verge():
    html = fetch_url("https://www.theverge.com/tech")
    if html.startswith("ERROR"):
        return []
    return extract_products_from_text(html_to_text(html), "theverge")


def scrape_producthunt():
    html = fetch_url("https://www.producthunt.com/feed")
    if html.startswith("ERROR"):
        return []
    return extract_products_from_text(html_to_text(html), "producthunt")


# ── Curation (Python, no AI) ───────────────────────────────────────────────

def deduplicate_products(all_products):
    seen = set()
    unique = []
    for p in all_products:
        key = re.sub(r'[^a-z0-9]', '', p["raw_text"].lower())[:50]
        if key not in seen and len(key) > 5:
            seen.add(key)
            unique.append(p)
    return unique


def auto_categorize(text):
    """Assign a category based on keyword matching."""
    text_lower = text.lower()
    scores = {}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        scores[cat] = sum(1 for kw in keywords if kw in text_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "Cool Gadgets and Gizmos"


def is_product_mention(text):
    """Check if text mentions an actual product (not just news)."""
    text_lower = text.lower()
    # Must contain a known brand
    has_brand = any(b.lower() in text_lower for b in BRANDS)
    # Filter out non-product news
    news_indicators = [
        "reportedly", "confirms", "demands", "lawsuit", "hacked", "hack",
        "ceo says", "scientists", "study", "research", "bacteria", "drug",
        "political", "government", "court", "police", "killed", "war",
        "election", "president", "senator", "congress", "fbi", "cia",
        "eradicate", "tumor", "cancer", "disease", "ransom", "arrest",
    ]
    is_news = any(ind in text_lower for ind in news_indicators)
    # Product indicators
    product_indicators = [
        "review", "launch", "announced", "release", "price", "buy",
        "sale", "deal", "hands-on", "specs", "battery", "display",
        "camera", "design", "upgrade", "gen ", "version", "model",
        "pro", "ultra", "max", "mini", "plus", "lite", "$",
    ]
    has_product_hint = any(ind in text_lower for ind in product_indicators)
    return (has_brand or has_product_hint) and not is_news


def curate_top_products(all_products, top_n=TOP_N):
    """Rank and select top N products. No AI — uses score + product filtering."""
    # Filter for actual products first
    product_posts = [p for p in all_products if is_product_mention(p["raw_text"])]
    
    # Sort by Reddit score (highest first)
    sorted_products = sorted(product_posts, key=lambda p: p.get("score", 0), reverse=True)

    selected = []
    seen_names = set()

    for p in sorted_products:
        if len(selected) >= top_n:
            break

        raw = p["raw_text"]
        # Extract a clean product name — look for brand + product pattern
        name = raw[:80]
        # Try to get a cleaner name by splitting on common separators
        for sep in [" review", " — ", " - ", " | ", ": "]:
            if sep in name.lower():
                name = name[:name.lower().index(sep)]
                break
        name = name.strip()[:60]

        if not name or len(name) < 5 or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())

        # Build the curated product
        category = auto_categorize(raw)
        description = raw[:150]
        score = p.get("score", 0)
        why = f"Trending on {p['source']}"
        if score > 0:
            why += f" ({score:,} upvotes)"

        # Category-specific hashtags
        HASHTAGS = {
            "Smart Home and IoT": "#SmartHome #IoT #HomeAutomation",
            "Phone and Tablet Accessories": "#PhoneTech #Smartphone #MobileGadgets",
            "Audio and Wearables": "#AudioTech #Wearables #TechStyle",
            "Cool Gadgets and Gizmos": "#CoolGadgets #TechGadgets #Innovation",
            "PC and Gaming Tech": "#GamingTech #PCGaming #TechDeals",
        }
        tags = HASHTAGS.get(category, "#TechGadgets #Trending")

        selected.append({
            "number": str(len(selected) + 1),
            "name": name,
            "category": category,
            "description": description,
            "why_trending": why,
            "price_range": "",
            "amazon_link": make_affiliate_link(name),
            "pin_caption": f"{name} — {description[:80]} {tags}",
            "image_1": "",
            "image_2": "",
        })

    return selected


# ── Image Scraping ──────────────────────────────────────────────────────────

def scrape_amazon_product_images(product_name, num_images=2):
    """Scrape product images from Amazon search results."""
    query = urllib.parse.quote_plus(product_name)
    url = f"https://www.amazon.com/s?k={query}"
    html = fetch_url(url, timeout=15)
    if html.startswith("ERROR"):
        return []

    bases = re.findall(
        r'(https://m\.media-amazon\.com/images/I/[A-Za-z0-9+%-]+)\._[^.]+_\.(?:jpg|png)',
        html,
    )
    unique_bases = list(dict.fromkeys(bases))

    images = []
    for base in unique_bases:
        if len(images) >= num_images:
            break
        img_id = base.split("/I/")[-1]
        if len(img_id) < 8:
            continue
        images.append({
            "large": f"{base}._AC_SL1500_.jpg",
            "medium": f"{base}._AC_SL1000_.jpg",
        })
    return images


def fetch_images_for_products(products):
    """Fetch Amazon images for each product."""
    for p in products:
        images = scrape_amazon_product_images(p["name"], num_images=2)
        if len(images) >= 1:
            p["image_1"] = images[0]["large"]
        if len(images) >= 2:
            p["image_2"] = images[1]["large"]
        time.sleep(1)  # rate limit
    return products


# ── CSV Generation ──────────────────────────────────────────────────────────

def generate_csv(products, path=CSV_PATH):
    """Write products to CSV file."""
    fields = ["Number", "Product Name", "Category", "Description", "Why Trending",
              "Price Range", "Amazon Link", "Pin Caption Idea", "Image 1", "Image 2"]

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for p in products:
            writer.writerow({
                "Number": p["number"],
                "Product Name": p["name"],
                "Category": p["category"],
                "Description": p["description"],
                "Why Trending": p["why_trending"],
                "Price Range": p["price_range"],
                "Amazon Link": p["amazon_link"],
                "Pin Caption Idea": p["pin_caption"],
                "Image 1": p["image_1"],
                "Image 2": p["image_2"],
            })
    return path


# ── Google Drive Upload ─────────────────────────────────────────────────────

def upload_csv_to_drive(csv_path, env):
    """Upload CSV to Google Drive PinterestAutomation folder."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        return None, "Google API libraries not installed"

    token_path = os.path.join(HERMES_HOME, "google_token.json")
    try:
        with open(token_path) as f:
            td = json.load(f)
    except FileNotFoundError:
        return None, "google_token.json not found"

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

    service = build("drive", "v3", credentials=creds)

    # Delete old CSVs before uploading new one
    old_csvs = service.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and mimeType='text/csv' and trashed=false",
        fields="files(id, name)",
        pageSize=50,
    ).execute().get("files", [])
    for f in old_csvs:
        service.files().delete(fileId=f["id"]).execute()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    file_metadata = {
        "name": f"trending_tech_products_{today}.csv",
        "parents": [DRIVE_FOLDER_ID],
        "mimeType": "text/csv",
    }
    media = MediaFileUpload(csv_path, mimetype="text/csv")
    file = service.files().create(
        body=file_metadata, media_body=media, fields="id,webViewLink"
    ).execute()
    return file.get("webViewLink", ""), None


# ── Email ───────────────────────────────────────────────────────────────────

def email_csv(csv_path, products, drive_link, env):
    """Email the CSV as attachment."""
    email_addr = env.get("EMAIL_ADDRESS", "")
    email_pass = env.get("EMAIL_PASSWORD", "")
    smtp_host = env.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(env.get("EMAIL_SMTP_PORT", "587"))

    if not email_addr or not email_pass:
        return "Email credentials not configured"

    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    
    msg = MIMEMultipart()
    msg["From"] = email_addr
    msg["To"] = email_addr
    msg["Subject"] = f"Daily Trending Tech Products for Pinterest - {today}"

    body = f"Trending Tech Products Report - {today}\n\n"
    body += f"{len(products)} products curated from 6 sources.\n"
    if drive_link:
        body += f"\nGoogle Drive: {drive_link}\n"
    body += "\nTop products:\n"
    for p in products[:5]:
        body += f"  - {p['name']} ({p['category']})\n"
    body += f"\n... and {len(products) - 5} more. See attached CSV for full list."

    msg.attach(MIMEText(body, "plain"))

    with open(csv_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition",
                        f"attachment; filename=trending_tech_products_{today}.csv")
        msg.attach(part)

    try:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(email_addr, email_pass)
        server.send_message(msg)
        server.quit()
        return None
    except Exception as e:
        return str(e)


# ── Telegram Report ─────────────────────────────────────────────────────────

def format_telegram_report(products, today_str):
    """Format the plain text Telegram report."""
    lines = []
    lines.append(f"DAILY TRENDING TECH PRODUCTS FOR PINTEREST")
    lines.append(f"{today_str}")
    lines.append("")

    # Group by category
    by_cat = {}
    for p in products:
        cat = p["category"]
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(p)

    for cat in CATEGORIES:
        if cat not in by_cat:
            continue
        lines.append(f"--- {cat.upper()} ---")
        lines.append("")
        for p in by_cat[cat]:
            lines.append(f"{p['number']}. {p['name']}")
            lines.append(f"{p['description'][:120]}")
            if p['price_range']:
                lines.append(f"Price: {p['price_range']}")
            lines.append(f"{p['amazon_link']}")
            lines.append("")

    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    today = datetime.now(timezone.utc)
    today_str = today.strftime("%B %d, %Y")
    env = load_env()

    send_telegram(f"🔍 Job 1 started: Scraping trending tech products ({today.strftime('%Y-%m-%d')})", env)

    # Step 1: Scrape all sources
    all_products = []
    sources_status = {}

    collectors = [
        ("reddit", scrape_reddit_gadgets),
        ("amazon", scrape_amazon_trending),
        ("google", scrape_google_trending_tech),
        ("techradar", scrape_techradar),
        ("theverge", scrape_verge),
        ("producthunt", scrape_producthunt),
    ]

    for name, fn in collectors:
        try:
            results = fn()
            all_products.extend(results)
            sources_status[name] = len(results)
        except Exception as e:
            sources_status[name] = 0

    # Step 2: Deduplicate and curate top 20
    unique = deduplicate_products(all_products)
    products = curate_top_products(unique, TOP_N)

    if not products:
        send_telegram("⚠️ Job 1: No products found from any source", env)
        print("No products found.")
        return

    send_telegram(f"📊 Scraped {len(all_products)} mentions, curated top {len(products)} products. Fetching images...", env)

    # Step 3: Fetch Amazon images
    products = fetch_images_for_products(products)
    img_count = sum(1 for p in products if p["image_1"])

    # Step 4: Generate CSV
    csv_path = generate_csv(products)

    # Step 5: Upload to Google Drive
    drive_link, drive_err = upload_csv_to_drive(csv_path, env)
    if drive_err:
        send_telegram(f"⚠️ Drive upload failed: {drive_err}", env)

    # Step 6: Email CSV
    email_err = email_csv(csv_path, products, drive_link, env)
    if email_err:
        send_telegram(f"⚠️ Email failed: {email_err}", env)

    # Step 7: Format and output Telegram report
    report = format_telegram_report(products, today_str)

    summary = f"✅ Job 1 complete: {len(products)} products, {img_count} with images"
    if drive_link:
        summary += f", CSV on Drive"
    if not email_err:
        summary += f", emailed"
    send_telegram(summary, env)

    # Output report (delivered to Telegram by Hermes)
    print(report)


if __name__ == "__main__":
    main()
