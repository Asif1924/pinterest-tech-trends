#!/usr/bin/env python3
"""
Trending Tech Products — HYBRID SCRAPING (Firecrawl + urllib)
Enhanced version with intelligent scraping method selection

Changes:
  - Uses Firecrawl for JS-heavy sites (Amazon, ProductHunt, etc.)
  - Falls back to urllib for simple/API endpoints (Reddit JSON)
  - Performance comparison tracking
  - Automatic retry with fallback on failure
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

# Import our Firecrawl hybrid client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from firecrawl_client import FirecrawlHybridClient

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

# Firecrawl setup
FIRECRAWL_CONFIG = CFG.get("firecrawl", {})
FIRECRAWL_API_KEY = FIRECRAWL_CONFIG.get("api_key", "")
FIRECRAWL_ENABLED = FIRECRAWL_CONFIG.get("enabled", False) and FIRECRAWL_API_KEY

# Initialize hybrid scraper
scraper = FirecrawlHybridClient(api_key=FIRECRAWL_API_KEY if FIRECRAWL_ENABLED else None)

# Existing config
TOP_N = CFG.get("top_n_products", 20)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT_HTTP = CFG.get("timeouts", {}).get("http_request", 15)
TIMEOUT_TELEGRAM = CFG.get("timeouts", {}).get("telegram_api", 10)
TIMEOUT_IMAGE = CFG.get("timeouts", {}).get("image_scrape", 15)
TIMEOUT_JOB2 = CFG.get("timeouts", {}).get("job2_subprocess", 120)
CSV_PATH = CFG.get("csv_path", "/tmp/trending_tech_products.csv")

# Links
LINK_STRATEGY = CFG.get("link_strategy", 2)
AFFILIATE_TAG = CFG.get("affiliate_tag", "allitechstore-20")


# ── Environment ─────────────────────────────────────────────────────────────
def load_env():
    """Load .env file."""
    env_path = os.path.join(HERMES_HOME, ".env")
    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip().strip('"')
    return env_vars


ENV = load_env()


# ── Telegram Notifications ──────────────────────────────────────────────────
def send_telegram(message):
    """Send message to Telegram."""
    bot_token = ENV.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = ENV.get("TELEGRAM_HOME_CHANNEL", "")
    
    if not bot_token or not chat_id:
        return
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = json.dumps({
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }).encode("utf-8")
        
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=TIMEOUT_TELEGRAM)
    except Exception:
        pass


# ── Product Tracking ────────────────────────────────────────────────────────
def load_procured_products():
    """Load list of already procured products."""
    procured_file = os.path.join(os.path.dirname(__file__), "procured_products.json")
    if os.path.exists(procured_file):
        try:
            with open(procured_file) as f:
                return json.load(f)
        except:
            return []
    return []


def check_if_procured(product_name, procured_list):
    """Check if product is already procured."""
    product_lower = product_name.lower()
    for procured in procured_list:
        if procured.lower() in product_lower or product_lower in procured.lower():
            return True
    return False


# ── Text Extraction ─────────────────────────────────────────────────────────
class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip = False
        
    def handle_starttag(self, tag, attrs):
        if tag in ["script", "style"]:
            self.skip = True
            
    def handle_endtag(self, tag):
        if tag in ["script", "style"]:
            self.skip = False
            
    def handle_data(self, data):
        if not self.skip:
            self.text.append(data)
            
    def get_text(self):
        return " ".join(self.text)


def html_to_text(html):
    parser = TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.get_text()


# ── Enhanced Scraping with Firecrawl ───────────────────────────────────────
def scrape_reddit_gadgets():
    """Scrape Reddit r/gadgets using JSON API (no Firecrawl needed)."""
    products = []
    try:
        # Reddit provides JSON API, no need for Firecrawl
        url = "https://www.reddit.com/r/gadgets/hot.json?limit=30"
        result, method = scraper.scrape_smart(url, prefer_firecrawl=False)
        
        if "error" not in result:
            data = json.loads(result.get("content", "{}"))
            for post in data.get("data", {}).get("children", []):
                p = post.get("data", {})
                products.append({
                    "name": p.get("title", ""),
                    "score": p.get("score", 0),
                    "url": p.get("url", ""),
                    "comments": p.get("num_comments", 0),
                    "source": "reddit"
                })
    except Exception as e:
        send_telegram(f"⚠️ Reddit scrape error: {str(e)[:100]}")
    
    return products


def scrape_amazon_trending():
    """Scrape Amazon Best Sellers using Firecrawl."""
    products = []
    categories = ["electronics", "computers", "wireless", "pc", "photo"]
    
    for cat in categories:
        url = f"https://www.amazon.com/Best-Sellers-{cat}/zgbs/{cat}"
        
        # Use Firecrawl for Amazon (JS-heavy site)
        result, method = scraper.scrape_smart(url, prefer_firecrawl=True)
        
        if "error" not in result:
            # Extract from markdown if Firecrawl succeeded
            if method == "firecrawl" and result.get("data"):
                content = result["data"].get("markdown", "")
                
                # Parse markdown for product names
                lines = content.split("\n")
                for line in lines:
                    if len(line) > 20 and not line.startswith("#"):
                        # Clean up product names
                        clean_name = re.sub(r'\[.*?\]', '', line)
                        clean_name = re.sub(r'\(.*?\)', '', clean_name)
                        clean_name = clean_name.strip()
                        
                        if len(clean_name) > 10:
                            products.append({
                                "name": clean_name[:100],
                                "source": f"amazon_{cat}",
                                "method": method
                            })
            else:
                # Fallback HTML parsing
                html = result.get("content", "")
                text = html_to_text(html)
                # Extract product patterns
                for match in re.findall(r'[A-Z][A-Za-z0-9\s\-,]+(?:Pro|Plus|Max|Mini|Ultra)?', text):
                    if 10 < len(match) < 100:
                        products.append({
                            "name": match.strip(),
                            "source": f"amazon_{cat}",
                            "method": method
                        })
    
    return products[:50]  # Limit to top 50


def scrape_google_trending_tech():
    """Scrape Google search results using Firecrawl."""
    products = []
    queries = ["trending tech gadgets 2024", "new technology products", "cool gadgets"]
    
    for query in queries:
        # Use Firecrawl search endpoint if available
        if scraper.has_firecrawl:
            result = scraper.search_web(query, limit=10)
            if "error" not in result and result.get("data"):
                for item in result["data"]:
                    title = item.get("title", "")
                    if title:
                        products.append({
                            "name": title,
                            "source": "google_search",
                            "method": "firecrawl_search"
                        })
        else:
            # Fallback to Google scraping
            url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}&num=15"
            result, method = scraper.scrape_smart(url, prefer_firecrawl=False)
            
            if "error" not in result:
                text = html_to_text(result.get("content", ""))
                for match in re.findall(r'[A-Z][A-Za-z0-9\s\-]+(?:Pro|Plus|Max|Mini)?', text):
                    if 10 < len(match) < 60:
                        products.append({
                            "name": match.strip(),
                            "source": "google",
                            "method": method
                        })
    
    return products


def scrape_techradar():
    """Scrape TechRadar using Firecrawl."""
    products = []
    url = "https://www.techradar.com/best/best-gadgets"
    
    result, method = scraper.scrape_smart(url, prefer_firecrawl=True)
    
    if "error" not in result:
        if method == "firecrawl" and result.get("data"):
            # Extract from clean markdown
            content = result["data"].get("markdown", "")
            # Look for product mentions
            for line in content.split("\n"):
                if any(keyword in line.lower() for keyword in ["best", "top", "great", "excellent"]):
                    # Extract product name patterns
                    matches = re.findall(r'(?:The\s+)?([A-Z][A-Za-z0-9\s\-]+(?:Pro|Plus|Max|Mini|Ultra)?)', line)
                    for match in matches:
                        if 10 < len(match) < 80:
                            products.append({
                                "name": match.strip(),
                                "source": "techradar",
                                "method": method
                            })
        else:
            # Fallback HTML parsing
            text = html_to_text(result.get("content", ""))
            products.extend(extract_product_names(text, "techradar", method))
    
    return products


def scrape_verge():
    """Scrape The Verge using Firecrawl."""
    url = "https://www.theverge.com/tech"
    result, method = scraper.scrape_smart(url, prefer_firecrawl=True)
    
    products = []
    if "error" not in result:
        if method == "firecrawl" and result.get("data"):
            content = result["data"].get("markdown", "")
            products.extend(extract_product_names(content, "theverge", method))
        else:
            text = html_to_text(result.get("content", ""))
            products.extend(extract_product_names(text, "theverge", method))
    
    return products


def scrape_producthunt():
    """Scrape Product Hunt using Firecrawl."""
    url = "https://www.producthunt.com/feed"
    result, method = scraper.scrape_smart(url, prefer_firecrawl=True)
    
    products = []
    if "error" not in result:
        if method == "firecrawl" and result.get("data"):
            content = result["data"].get("markdown", "")
            # Extract product names from markdown
            lines = content.split("\n")
            for line in lines:
                # Look for product-like patterns
                if not line.startswith("#") and len(line) > 5:
                    clean = re.sub(r'\[.*?\]|\(.*?\)', '', line).strip()
                    if 5 < len(clean) < 80:
                        products.append({
                            "name": clean,
                            "source": "producthunt",
                            "method": method
                        })
        else:
            text = html_to_text(result.get("content", ""))
            products.extend(extract_product_names(text, "producthunt", method))
    
    return products[:30]


def extract_product_names(text, source, method):
    """Extract product names from text."""
    products = []
    # Common product name patterns
    patterns = [
        r'(?:The\s+)?([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*(?:\s+(?:Pro|Plus|Max|Mini|Ultra|Air|Lite|X|S|SE|XL|2|3|4|5|6|7|8|9|10))?)',
        r'([A-Z][a-z]+[A-Z][a-z]+)',  # CamelCase products
        r'([A-Z]{2,}[\s\-]?[0-9]+)',  # Model numbers
    ]
    
    seen = set()
    for pattern in patterns:
        for match in re.findall(pattern, text):
            if isinstance(match, tuple):
                match = match[0]
            match = match.strip()
            if 5 < len(match) < 80 and match not in seen:
                seen.add(match)
                products.append({
                    "name": match,
                    "source": source,
                    "method": method
                })
    
    return products


# ── Affiliate Links ─────────────────────────────────────────────────────────
def affiliate_link_strategy_1(product_name, affiliate_tag=None):
    """Strategy 1: Search Links — always works, lower conversion."""
    tag = affiliate_tag or AFFILIATE_TAG
    terms = urllib.parse.quote_plus(product_name)
    return f"https://www.amazon.com/s?k={terms}&tag={tag}"


def affiliate_link_strategy_2(product_name, affiliate_tag=None):
    """Strategy 2: Direct Product Links using Firecrawl."""
    tag = affiliate_tag or AFFILIATE_TAG
    
    # Try Firecrawl first for better extraction
    if scraper.has_firecrawl:
        query = urllib.parse.quote_plus(product_name)
        url = f"https://www.amazon.com/s?k={query}"
        
        # Use Firecrawl's extract feature for product data
        products = scraper.extract_products(url)
        if products and len(products) > 0:
            # Get first product's link
            product_link = products[0].get("link", "")
            # Extract ASIN from link
            asin_match = re.search(r'/dp/([A-Z0-9]{10})', product_link)
            if asin_match:
                asin = asin_match.group(1)
                return f"https://www.amazon.com/dp/{asin}?tag={tag}"
    
    # Fallback to original method
    query = urllib.parse.quote_plus(product_name)
    url = f"https://www.amazon.com/s?k={query}"
    result, _ = scraper.scrape_smart(url, prefer_firecrawl=False)
    
    if "error" not in result:
        html = result.get("content", "")
        # Look for ASIN patterns
        asin_patterns = [
            r'data-asin="([A-Z0-9]{10})"',
            r'/dp/([A-Z0-9]{10})',
            r'asin=([A-Z0-9]{10})',
        ]
        
        for pattern in asin_patterns:
            match = re.search(pattern, html)
            if match:
                asin = match.group(1)
                return f"https://www.amazon.com/dp/{asin}?tag={tag}"
    
    # Fallback to search link
    return affiliate_link_strategy_1(product_name, affiliate_tag)


# ── Image Scraping ──────────────────────────────────────────────────────────
def scrape_amazon_product_images(product_name, num_images=2):
    """Scrape Amazon product images using Firecrawl."""
    images = []
    
    # Try Firecrawl extraction first
    if scraper.has_firecrawl:
        query = urllib.parse.quote_plus(product_name)
        url = f"https://www.amazon.com/s?k={query}"
        products = scraper.extract_products(url)
        
        if products:
            for product in products[:num_images]:
                img_url = product.get("image", "")
                if img_url and img_url.startswith("http"):
                    images.append(img_url)
            
            if images:
                return images
    
    # Fallback to HTML scraping
    query = urllib.parse.quote_plus(product_name)
    url = f"https://www.amazon.com/s?k={query}"
    result, _ = scraper.scrape_smart(url, prefer_firecrawl=False)
    
    if "error" not in result:
        html = result.get("content", "")
        # Extract image URLs
        img_patterns = [
            r'<img[^>]+src="(https://[^"]+\.jpg)"',
            r'data-image-source-url="(https://[^"]+)"',
            r'"hiRes":"(https://[^"]+)"',
        ]
        
        for pattern in img_patterns:
            matches = re.findall(pattern, html)
            for match in matches[:num_images]:
                if "product" in match.lower() or "image" in match.lower():
                    images.append(match)
                    if len(images) >= num_images:
                        return images
    
    return images


def fetch_images_for_products(products):
    """Fetch images for all products."""
    for p in products:
        images = scrape_amazon_product_images(p["name"], num_images=2)
        p["images"] = images
    return products


# ── Main Pipeline ───────────────────────────────────────────────────────────
def main():
    print("🔥 Starting Trending Tech Products Scraper (Hybrid Mode)")
    send_telegram("🔥 <b>Job 1 Starting:</b> Trending Tech Products Scraper (Hybrid Mode)")
    
    # Track performance
    start_time = time.time()
    
    # Load procured products
    procured_list = load_procured_products()
    
    # Scrape all sources
    all_products = []
    sources = [
        ("reddit", scrape_reddit_gadgets), 
        ("amazon", scrape_amazon_trending),
        ("google", scrape_google_trending_tech), 
        ("techradar", scrape_techradar),
        ("theverge", scrape_verge), 
        ("producthunt", scrape_producthunt),
    ]
    
    for source_name, scrape_func in sources:
        print(f"  Scraping {source_name}...")
        try:
            products = scrape_func()
            all_products.extend(products)
            print(f"    Found {len(products)} products")
        except Exception as e:
            print(f"    Error: {e}")
            send_telegram(f"⚠️ {source_name} scrape failed: {str(e)[:100]}")
    
    # Score and rank products
    product_scores = {}
    for p in all_products:
        name = p.get("name", "").strip()
        if not name or len(name) < 5:
            continue
            
        # Normalize name
        name_key = re.sub(r'[^\w\s]', '', name.lower())[:50]
        
        if name_key not in product_scores:
            product_scores[name_key] = {
                "name": name,
                "score": 0,
                "sources": [],
                "reddit_score": 0,
                "method": p.get("method", "unknown")
            }
        
        # Scoring
        product_scores[name_key]["score"] += 1
        product_scores[name_key]["sources"].append(p.get("source", "unknown"))
        
        if p.get("source") == "reddit":
            product_scores[name_key]["reddit_score"] = p.get("score", 0)
            product_scores[name_key]["score"] += p.get("score", 0) / 100
    
    # Sort by score
    sorted_products = sorted(
        product_scores.values(),
        key=lambda x: (x["score"], x["reddit_score"]),
        reverse=True
    )
    
    # Get top N products
    products = sorted_products[:TOP_N]
    
    # Check procurement status
    for p in products:
        p["procured"] = check_if_procured(p["name"], procured_list)
    
    # Generate affiliate links
    for p in products:
        if LINK_STRATEGY == 2:
            p["link"] = affiliate_link_strategy_2(p["name"])
        else:
            p["link"] = affiliate_link_strategy_1(p["name"])
    
    # Fetch images
    print("  Fetching product images...")
    products = fetch_images_for_products(products)
    
    # Save CSV
    print(f"  Saving CSV to {CSV_PATH}")
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "link", "images", "score", "sources", "procured"])
        writer.writeheader()
        for p in products:
            writer.writerow({
                "name": p["name"],
                "link": p["link"],
                "images": "|".join(p.get("images", [])),
                "score": round(p["score"], 2),
                "sources": ",".join(set(p["sources"])),
                "procured": "YES" if p["procured"] else "NO"
            })
    
    # Send email report
    send_email_report(products)
    
    # Send Telegram report
    telegram_msg = ["<b>📊 Top 20 Trending Tech Products</b>", ""]
    
    new_count = sum(1 for p in products if not p["procured"])
    telegram_msg.append(f"🆕 New Products: {new_count}/{len(products)}")
    telegram_msg.append("")
    
    for i, p in enumerate(products, 1):
        status = "✅" if p["procured"] else "🆕"
        method = p.get("method", "unknown")
        telegram_msg.append(f"{i}. {status} <b>{p['name']}</b>")
        telegram_msg.append(f"   Score: {p['score']:.1f} | Method: {method}")
        telegram_msg.append(f"   Sources: {', '.join(set(p['sources']))}")
        telegram_msg.append("")
    
    # Add performance stats
    elapsed = time.time() - start_time
    telegram_msg.append(scraper.get_stats_report())
    telegram_msg.append(f"\n⏱️ Total time: {elapsed:.1f}s")
    
    send_telegram("\n".join(telegram_msg))
    
    # Trigger Job 2
    print("  Triggering Job 2 (Pin Generator)...")
    try:
        script_path = os.path.join(os.path.dirname(__file__), "pinterest_pin_generator.py")
        subprocess.run([sys.executable, script_path], timeout=TIMEOUT_JOB2, check=True)
        print("  ✅ Job 2 completed successfully")
        send_telegram("✅ <b>Job 2 Complete:</b> Pinterest pins generated")
    except subprocess.TimeoutExpired:
        print("  ⚠️ Job 2 timed out")
        send_telegram("⚠️ Job 2 timed out after 2 minutes")
    except Exception as e:
        print(f"  ❌ Job 2 failed: {e}")
        send_telegram(f"❌ Job 2 failed: {str(e)[:200]}")
    
    print("✅ Pipeline complete!")
    send_telegram("✅ <b>Pipeline Complete!</b> All jobs finished.")


def send_email_report(products):
    """Send email report with products."""
    email_address = ENV.get("EMAIL_ADDRESS", "")
    email_password = ENV.get("EMAIL_PASSWORD", "")
    
    if not email_address or not email_password:
        return
    
    try:
        # Create HTML email
        html_body = create_html_report(products)
        
        msg = MIMEMultipart()
        msg["From"] = email_address
        msg["To"] = email_address
        msg["Subject"] = f"Trending Tech Products - {datetime.now().strftime('%Y-%m-%d')}"
        
        msg.attach(MIMEText(html_body, "html"))
        
        # Attach CSV
        with open(CSV_PATH, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename=trending_tech_products.csv")
            msg.attach(part)
        
        # Send email
        server = smtplib.SMTP(CFG.get("smtp_defaults", {}).get("host", "smtp.gmail.com"), 
                              CFG.get("smtp_defaults", {}).get("port", 587))
        server.starttls()
        server.login(email_address, email_password)
        server.send_message(msg)
        server.quit()
        
        print("  ✅ Email sent successfully")
    except Exception as e:
        print(f"  ❌ Email failed: {e}")


def create_html_report(products):
    """Create HTML email report."""
    html = [
        "<html><body>",
        "<h2>Trending Tech Products Report</h2>",
        f"<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>",
        f"<p>Scraping Method: Hybrid (Firecrawl + urllib)</p>",
        "<table border='1' cellpadding='5'>",
        "<tr><th>#</th><th>Status</th><th>Product</th><th>Score</th><th>Sources</th><th>Method</th><th>Link</th></tr>"
    ]
    
    for i, p in enumerate(products, 1):
        status = "✅ Procured" if p.get("procured") else "🆕 NEW"
        method = p.get("method", "unknown")
        html.append(f"<tr>")
        html.append(f"<td>{i}</td>")
        html.append(f"<td>{status}</td>")
        html.append(f"<td><b>{p['name']}</b></td>")
        html.append(f"<td>{p['score']:.1f}</td>")
        html.append(f"<td>{', '.join(set(p['sources']))}</td>")
        html.append(f"<td>{method}</td>")
        html.append(f"<td><a href='{p['link']}'>View</a></td>")
        html.append(f"</tr>")
    
    html.append("</table>")
    
    # Add performance stats
    html.append("<h3>Scraping Performance</h3>")
    html.append(f"<pre>{scraper.get_stats_report()}</pre>")
    
    html.append("</body></html>")
    
    return "\n".join(html)


if __name__ == "__main__":
    main()