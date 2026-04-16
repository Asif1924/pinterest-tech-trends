#!/usr/bin/env python3
"""
Trending Tech Products — FULLY AUTOMATED (no AI needed)

Complete pipeline in one script:
  1. Scrapes 6 sources for trending tech products
  2. Curates top 20 by Reddit score + product filtering
  3. Fetches 2 Amazon product images per product
  4. Generates CSV with all data
  5. Emails CSV report to inbox
  6. Sends formatted Telegram report
  7. Triggers Job 2 (pin generator) immediately
  8. Triggers Job 3 (pin uploader)

All settings in pinterest_config.json — no hardcoded values.
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
import subprocess
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
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pinterest_config.json")


def load_config():
    """Load config from pinterest_config.json."""
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


CFG = load_config()
AFFILIATE_TAG = CFG.get("affiliate_tag", "allitechstore-20")
TOP_N = CFG.get("top_n_products", 20)
CSV_PATH = CFG.get("csv_path", "/tmp/trending_tech_products.csv")
DRIVE_FOLDER_ID = CFG.get("google_drive", {}).get("automation_folder_id", "")
TIMEOUT_HTTP = CFG.get("timeouts", {}).get("http_request", 15)
TIMEOUT_TELEGRAM = CFG.get("timeouts", {}).get("telegram_api", 10)
TIMEOUT_IMAGE = CFG.get("timeouts", {}).get("image_scrape", 15)
TIMEOUT_JOB2 = CFG.get("timeouts", {}).get("job2_subprocess", 120)
SMTP_HOST = CFG.get("smtp_defaults", {}).get("host", "smtp.gmail.com")
SMTP_PORT = CFG.get("smtp_defaults", {}).get("port", 587)

CATEGORIES = [
    "Smart Home and IoT",
    "Phone and Tablet Accessories",
    "Audio and Wearables",
    "Cool Gadgets and Gizmos",
    "PC and Gaming Tech",
]

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

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


# ── Helpers ─────────────────────────────────────────────────────────────────

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


def send_telegram(text, env=None):
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
        urllib.request.urlopen(req, timeout=TIMEOUT_TELEGRAM)
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


def fetch_url(url, timeout=None):
    if timeout is None:
        timeout = TIMEOUT_HTTP
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


# ── Affiliate Link Strategies ───────────────────────────────────────────────

def affiliate_link_strategy_1(product_name, affiliate_tag=None):
    """Strategy 1: Search Links — always works, lower conversion."""
    tag = affiliate_tag or AFFILIATE_TAG
    terms = urllib.parse.quote_plus(product_name)
    return f"https://www.amazon.com/s?k={terms}&tag={tag}"


def affiliate_link_strategy_2(product_name, affiliate_tag=None):
    """Strategy 2: Direct Product Links — higher conversion, scrapes ASIN."""
    tag = affiliate_tag or AFFILIATE_TAG
    query = urllib.parse.quote_plus(product_name)
    url = f"https://www.amazon.com/s?k={query}"
    html = fetch_url(url, timeout=TIMEOUT_IMAGE)
    if html.startswith("ERROR"):
        return affiliate_link_strategy_1(product_name, tag)

    asins = re.findall(r'data-asin="([A-Z0-9]{10})"', html)
    seen = set()
    unique = []
    for a in asins:
        if a and a not in seen:
            seen.add(a)
            unique.append(a)

    if unique:
        return f"https://www.amazon.com/dp/{unique[0]}?tag={tag}"
    return affiliate_link_strategy_1(product_name, tag)


_STRATEGIES = {1: affiliate_link_strategy_1, 2: affiliate_link_strategy_2}


def make_affiliate_link(product_name):
    strategy = CFG.get("link_strategy", 1)
    fn = _STRATEGIES.get(strategy, affiliate_link_strategy_1)
    return fn(product_name)


# ── Scrapers ────────────────────────────────────────────────────────────────

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
                        "raw_text": title, "source": f"reddit/r/{sub}",
                        "score": score, "url": post.get("url", ""),
                    })
        except (json.JSONDecodeError, KeyError):
            continue
        time.sleep(1)
    return products


def scrape_amazon_trending():
    products = []
    for url in [
        "https://www.amazon.com/gp/moversandshakers/electronics/",
        "https://www.amazon.com/Best-Sellers-Electronics/zgbs/electronics/",
    ]:
        html = fetch_url(url)
        if not html.startswith("ERROR"):
            products.extend(extract_products_from_text(html_to_text(html), "amazon"))
        time.sleep(1)
    return products


def scrape_google_trending_tech():
    products = []
    for query in ["trending tech products this week", "best selling gadgets on Amazon electronics", "coolest new tech gadgets this month"]:
        html = fetch_url(f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}&num=15")
        if not html.startswith("ERROR"):
            products.extend(extract_products_from_text(html_to_text(html), f"google:{query[:30]}"))
        time.sleep(2)
    return products


def scrape_techradar():
    html = fetch_url("https://www.techradar.com/best/best-gadgets")
    return [] if html.startswith("ERROR") else extract_products_from_text(html_to_text(html), "techradar")


def scrape_verge():
    html = fetch_url("https://www.theverge.com/tech")
    return [] if html.startswith("ERROR") else extract_products_from_text(html_to_text(html), "theverge")


def scrape_producthunt():
    html = fetch_url("https://www.producthunt.com/feed")
    return [] if html.startswith("ERROR") else extract_products_from_text(html_to_text(html), "producthunt")


# ── Curation ────────────────────────────────────────────────────────────────

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
    text_lower = text.lower()
    scores = {cat: sum(1 for kw in kws if kw in text_lower) for cat, kws in CATEGORY_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "Cool Gadgets and Gizmos"


def is_product_mention(text):
    text_lower = text.lower()
    has_brand = any(b.lower() in text_lower for b in BRANDS)
    news_words = ["reportedly", "confirms", "demands", "lawsuit", "hacked", "hack",
        "ceo says", "scientists", "study", "research", "bacteria", "drug",
        "political", "government", "court", "police", "killed", "war",
        "election", "president", "senator", "congress", "fbi", "cia",
        "eradicate", "tumor", "cancer", "disease", "ransom", "arrest"]
    is_news = any(w in text_lower for w in news_words)
    product_words = ["review", "launch", "announced", "release", "price", "buy",
        "sale", "deal", "hands-on", "specs", "battery", "display", "camera",
        "design", "upgrade", "gen ", "version", "model", "pro", "ultra",
        "max", "mini", "plus", "lite", "$"]
    has_product = any(w in text_lower for w in product_words)
    return (has_brand or has_product) and not is_news


HASHTAGS = {
    "Smart Home and IoT": "#SmartHome #IoT #HomeAutomation",
    "Phone and Tablet Accessories": "#PhoneTech #Smartphone #MobileGadgets",
    "Audio and Wearables": "#AudioTech #Wearables #TechStyle",
    "Cool Gadgets and Gizmos": "#CoolGadgets #TechGadgets #Innovation",
    "PC and Gaming Tech": "#GamingTech #PCGaming #TechDeals",
}


def curate_top_products(all_products):
    product_posts = [p for p in all_products if is_product_mention(p["raw_text"])]
    sorted_products = sorted(product_posts, key=lambda p: p.get("score", 0), reverse=True)

    selected = []
    seen_names = set()

    for p in sorted_products:
        if len(selected) >= TOP_N:
            break
        raw = p["raw_text"]
        name = raw[:80]
        for sep in [" review", " — ", " - ", " | ", ": "]:
            if sep in name.lower():
                name = name[:name.lower().index(sep)]
                break
        name = name.strip()[:60]
        if not name or len(name) < 5 or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())

        category = auto_categorize(raw)
        score = p.get("score", 0)
        why = f"Trending on {p['source']}"
        if score > 0:
            why += f" ({score:,} upvotes)"
        tags = HASHTAGS.get(category, "#TechGadgets #Trending")

        selected.append({
            "number": str(len(selected) + 1), "name": name,
            "category": category, "description": raw[:150],
            "why_trending": why, "price_range": "",
            "amazon_link": make_affiliate_link(name),
            "pin_caption": f"{name} — {raw[:80]} {tags}",
            "image_1": "", "image_2": "",
        })
    return selected


# ── Image Scraping ──────────────────────────────────────────────────────────

def scrape_amazon_product_images(product_name, num_images=2):
    query = urllib.parse.quote_plus(product_name)
    html = fetch_url(f"https://www.amazon.com/s?k={query}", timeout=TIMEOUT_IMAGE)
    if html.startswith("ERROR"):
        return []
    bases = re.findall(
        r'(https://m\.media-amazon\.com/images/I/[A-Za-z0-9+%-]+)\._[^.]+_\.(?:jpg|png)', html)
    unique_bases = list(dict.fromkeys(bases))
    images = []
    for base in unique_bases:
        if len(images) >= num_images:
            break
        if len(base.split("/I/")[-1]) < 8:
            continue
        images.append({"large": f"{base}._AC_SL1500_.jpg", "medium": f"{base}._AC_SL1000_.jpg"})
    return images


def fetch_images_for_products(products):
    for p in products:
        images = scrape_amazon_product_images(p["name"], num_images=2)
        if len(images) >= 1:
            p["image_1"] = images[0]["large"]
        if len(images) >= 2:
            p["image_2"] = images[1]["large"]
        time.sleep(1)
    return products


# ── CSV Generation ──────────────────────────────────────────────────────────

def generate_csv(products):
    fields = ["Number", "Product Name", "Category", "Description", "Why Trending",
              "Price Range", "Amazon Link", "Pin Caption Idea", "Image 1", "Image 2", "Procured"]
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for p in products:
            writer.writerow({
                "Number": p["number"], "Product Name": p["name"],
                "Category": p["category"], "Description": p["description"],
                "Why Trending": p["why_trending"], "Price Range": p["price_range"],
                "Amazon Link": p["amazon_link"], "Pin Caption Idea": p["pin_caption"],
                "Image 1": p["image_1"], "Image 2": p["image_2"],
                "Procured": "Yes" if p.get("procured", False) else "No",
            })
    return CSV_PATH


# ── Google Drive Upload ─────────────────────────────────────────────────────

def upload_csv_to_drive(csv_path, env):
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
        fields="files(id, name)", pageSize=50,
    ).execute().get("files", [])
    for f in old_csvs:
        service.files().delete(fileId=f["id"]).execute()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    file_metadata = {
        "name": f"trending_tech_products_{today}.csv",
        "parents": [DRIVE_FOLDER_ID], "mimeType": "text/csv",
    }
    media = MediaFileUpload(csv_path, mimetype="text/csv")
    file = service.files().create(
        body=file_metadata, media_body=media, fields="id,webViewLink"
    ).execute()
    return file.get("webViewLink", ""), None


# ── Email ───────────────────────────────────────────────────────────────────

def email_csv(csv_path, products, drive_link, env):
    email_addr = env.get("EMAIL_ADDRESS", "")
    email_pass = env.get("EMAIL_PASSWORD", "")
    smtp_host = env.get("EMAIL_SMTP_HOST", SMTP_HOST)
    smtp_port = int(env.get("EMAIL_SMTP_PORT", str(SMTP_PORT)))

    if not email_addr or not email_pass:
        return "Email credentials not configured"

    # Load procured products list
    procured_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "procured_products.json")
    procured_list = []
    try:
        with open(procured_file) as f:
            procured_data = json.load(f)
            procured_list = [p.lower() for p in procured_data.get("procured", [])]
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Mark products as procured or new
    new_products = []
    procured_products = []
    for p in products:
        is_procured = any(proc in p['name'].lower() for proc in procured_list)
        p['procured'] = is_procured
        if is_procured:
            procured_products.append(p)
        else:
            new_products.append(p)

    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    msg = MIMEMultipart()
    msg["From"] = email_addr
    msg["To"] = email_addr
    msg["Subject"] = f"Daily Trending Tech Products for Pinterest - {today}"

    body = f"Trending Tech Products Report - {today}\n\n"
    body += f"Total: {len(products)} products | New: {len(new_products)} | Already Procured: {len(procured_products)}\n"
    body += "=" * 60 + "\n"
    
    if drive_link:
        body += f"\nGoogle Drive: {drive_link}\n"
    
    if new_products:
        body += f"\n🆕 NEW PRODUCTS TO CONSIDER ({len(new_products)}):\n"
        body += "-" * 40 + "\n"
        for i, p in enumerate(new_products[:10], 1):
            body += f"{i}. {p['name']}\n"
            body += f"   Category: {p['category']}\n"
            body += f"   Why Trending: {p['why_trending']}\n"
            if p.get('price_range'):
                body += f"   Price: {p['price_range']}\n"
            body += "\n"
        if len(new_products) > 10:
            body += f"... and {len(new_products) - 10} more new products in the CSV.\n"
    
    if procured_products:
        body += f"\n✓ ALREADY PROCURED ({len(procured_products)}):\n"
        body += "-" * 40 + "\n"
        for p in procured_products[:5]:
            body += f"  • {p['name']} ({p['category']})\n"
        if len(procured_products) > 5:
            body += f"  ... and {len(procured_products) - 5} more.\n"
    
    body += "\n" + "=" * 60 + "\n"
    body += "See attached CSV for full details including Amazon links and image URLs.\n"
    body += "\nTo mark products as procured, update: procured_products.json"

    msg.attach(MIMEText(body, "plain"))
    with open(csv_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        file_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        part.add_header("Content-Disposition",
                        f"attachment; filename=trending_tech_products_{file_timestamp}.csv")
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
    lines = [f"DAILY TRENDING TECH PRODUCTS FOR PINTEREST", today_str, ""]
    
    # Count procured vs new
    new_count = sum(1 for p in products if not p.get("procured", False))
    procured_count = sum(1 for p in products if p.get("procured", False))
    lines.append(f"Total: {len(products)} | New: {new_count} | Procured: {procured_count}")
    lines.append("")
    
    by_cat = {}
    for p in products:
        by_cat.setdefault(p["category"], []).append(p)
    for cat in CATEGORIES:
        if cat not in by_cat:
            continue
        lines.extend([f"--- {cat.upper()} ---", ""])
        for p in by_cat[cat]:
            status = " ✓" if p.get("procured", False) else " 🆕"
            lines.append(f"{p['number']}.{status} {p['name']}")
            lines.append(p['description'][:120])
            if p['price_range']:
                lines.append(f"Price: {p['price_range']}")
            lines.extend([p['amazon_link'], ""])
    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    today = datetime.now(timezone.utc)
    today_str = today.strftime("%B %d, %Y")
    env = load_env()

    send_telegram(f"🚀 Job 1 started at {today.strftime('%Y-%m-%d %H:%M:%S UTC')}", env)

    strategy = CFG.get("link_strategy", 1)
    strategy_name = CFG.get("link_strategies", {}).get(str(strategy), {}).get("name", f"Strategy {strategy}")
    send_telegram(f"🔍 Job 1 started: Scraping trending tech products ({today.strftime('%Y-%m-%d')})\nAffiliate links: {strategy_name}", env)

    # Step 1: Scrape all sources
    all_products = []
    for name, fn in [
        ("reddit", scrape_reddit_gadgets), ("amazon", scrape_amazon_trending),
        ("google", scrape_google_trending_tech), ("techradar", scrape_techradar),
        ("theverge", scrape_verge), ("producthunt", scrape_producthunt),
    ]:
        try:
            all_products.extend(fn())
        except Exception:
            pass

    # Step 2: Curate top N
    unique = deduplicate_products(all_products)
    products = curate_top_products(unique)

    if not products:
        send_telegram("⚠️ Job 1: No products found from any source", env)
        send_telegram(f"🏁 Job 1 ended at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}", env)
        print("No products found.")
        return

    send_telegram(f"📊 Scraped {len(all_products)} mentions, curated top {len(products)} products. Fetching images...", env)

    # Step 3: Fetch Amazon images
    products = fetch_images_for_products(products)
    img_count = sum(1 for p in products if p["image_1"])

    # Step 3.5: Mark procured products
    procured_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "procured_products.json")
    procured_list = []
    try:
        with open(procured_file) as f:
            procured_data = json.load(f)
            procured_list = [p.lower() for p in procured_data.get("procured", [])]
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    
    for p in products:
        p["procured"] = any(proc in p['name'].lower() for proc in procured_list)

    # Step 4: Generate CSV
    csv_path = generate_csv(products)

    # Step 5: Email CSV (no Google Drive upload)
    email_err = email_csv(csv_path, products, None, env)  # No drive_link
    if email_err:
        send_telegram(f"⚠️ Email failed: {email_err}", env)

    # Step 6: Send Telegram Summary
    report = format_telegram_report(products, today_str)
    summary = f"✅ Job 1 complete: {len(products)} products, {img_count} with images"
    if not email_err:
        summary += ", emailed report"
    send_telegram(summary, env)
    
    # Also send the detailed report to Telegram
    send_telegram(report, env)

    # Step 7: Chain Job 2 (Pinterest Pin Generator) immediately
    # Job 2 will automatically chain Job 3 when it completes
    try:
        print("\n🔗 Chaining Job 2 (Pinterest Pin Generator)...")
        pin_gen_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pinterest_pin_generator.py")
        result = subprocess.run(
            [sys.executable, pin_gen_script],
            capture_output=True, text=True, timeout=TIMEOUT_JOB2,
        )
        
        if result.stdout.strip() and result.stdout.strip() != "[SILENT]":
            print("--- JOB 2 OUTPUT ---")
            print(result.stdout.strip())
        
        if result.returncode == 0:
            # Job 2 succeeded - it will chain Job 3 automatically
            pins_created = "pins created: 0" not in result.stdout.lower() and "total pins created: 0" not in result.stdout.lower()
            if pins_created:
                send_telegram("✅ Job 2 chained successfully: Pinterest pins generated and emailed (Job 3 will upload automatically)", env)
            else:
                send_telegram("⚠️ Job 2 completed but no pins created (possibly no new products)", env)
        else:
            error_msg = result.stderr[:200] if result.stderr else "Unknown error"
            send_telegram(f"❌ Job 2 chaining failed: {error_msg}", env)
            
    except subprocess.TimeoutExpired:
        send_telegram(f"⏰ Job 2 chaining timed out after {TIMEOUT_JOB2} seconds", env)
    except Exception as e:
        send_telegram(f"❌ Job 2 chaining error: {str(e)[:200]}", env)

    send_telegram(f"🏁 Job 1 ended at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}", env)

    # Output report
    print(report)


if __name__ == "__main__":
    main()
