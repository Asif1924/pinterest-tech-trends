#!/usr/bin/env python3
"""
Trending Tech Products Data Collector
Scrapes multiple sources for trending tech/gadget/electronics products,
deduplicates, and outputs structured JSON for the cron job agent.

Sources:
  1. Amazon Best Sellers - Electronics / Movers & Shakers
  2. Google Trends / Google Shopping trending
  3. Reddit r/gadgets, r/technology hot posts
  4. Product Hunt trending tech
  5. TikTok viral tech (via web search)

Output: JSON to stdout with product data + metadata.
The cron job agent uses this as context to compile the final report.
"""

# ── Venv bootstrap ──────────────────────────────────────────────────────────
# When Hermes runs this script via `sys.executable script.py`, it uses Hermes's
# own Python, not our dedicated venv. This block detects that and re-execs with
# the correct venv Python so all pip-installed dependencies are available.
import os
import sys
from pathlib import Path

_VENV_DIR = Path(__file__).resolve().parent / ".venv"
_VENV_PYTHON = _VENV_DIR / "bin" / "python3"

if _VENV_PYTHON.exists() and os.environ.get("_PTT_VENV_ACTIVE") != "1":
    os.environ["_PTT_VENV_ACTIVE"] = "1"
    os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON), *sys.argv])
# ── End venv bootstrap ──────────────────────────────────────────────────────

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

AFFILIATE_TAG = "allitechstore-20"
CATEGORIES = [
    "Smart Home and IoT",
    "Phone and Tablet Accessories",
    "Audio and Wearables",
    "Cool Gadgets and Gizmos",
    "PC and Gaming Tech",
]

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class TextExtractor(HTMLParser):
    """Simple HTML to text extractor."""

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
    """Fetch a URL and return the response text."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"ERROR: {e}"


def html_to_text(html):
    """Strip HTML tags and return plain text."""
    parser = TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.get_text()


def make_affiliate_link(product_name):
    """Generate Amazon Associates search link."""
    terms = urllib.parse.quote_plus(product_name)
    return f"https://www.amazon.com/s?k={terms}&tag={AFFILIATE_TAG}"


def extract_products_from_text(text, source_name):
    """
    Try to extract product names/descriptions from scraped text.
    Returns a list of dicts with raw product info.
    """
    products = []
    # Look for common product name patterns
    # Lines that look like product listings: start with number, bullet, or product brand
    lines = text.split("\n")
    brands = [
        "Apple", "Samsung", "Google", "Sony", "Bose", "Anker", "Logitech",
        "Razer", "JBL", "Meta", "Amazon", "Ring", "Nanoleaf", "Govee",
        "Dyson", "Ember", "Keychron", "BenQ", "XREAL", "Oura", "Backbone",
        "SwitchBot", "Dreame", "Roborock", "ecobee", "Philips", "TP-Link",
        "Eufy", "DJI", "GoPro", "Kindle", "Nintendo", "Valve", "Steam",
        "Lenovo", "ASUS", "MSI", "Corsair", "SteelSeries", "HyperX",
        "Nothing", "OnePlus", "Xiaomi", "Shokz", "Garmin", "Fitbit",
        "Dell", "HP", "LG", "TCL", "Roku", "Sonos", "Marshall",
    ]
    brand_pattern = "|".join(re.escape(b) for b in brands)

    for line in lines:
        line = line.strip()
        if not line or len(line) < 10 or len(line) > 300:
            continue
        # Match lines containing known brand names with product info
        if re.search(brand_pattern, line, re.IGNORECASE):
            # Skip lines that are clearly not product names
            if any(skip in line.lower() for skip in [
                "cookie", "privacy", "sign in", "subscribe", "copyright",
                "terms of", "about us", "contact", "navigation", "menu",
                "advertisement", "sponsored",
            ]):
                continue
            products.append({
                "raw_text": line[:250],
                "source": source_name,
            })

    return products[:30]  # cap per source


def scrape_reddit_gadgets():
    """Fetch hot posts from r/gadgets and r/technology."""
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
        time.sleep(1)  # rate limit
    return products


def scrape_product_hunt():
    """Fetch trending tech from Product Hunt's feed."""
    url = "https://www.producthunt.com/feed"
    html = fetch_url(url)
    if html.startswith("ERROR"):
        return []
    text = html_to_text(html)
    return extract_products_from_text(text, "producthunt")


def scrape_amazon_trending():
    """Fetch Amazon best sellers / movers and shakers in electronics."""
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
    """Search Google for trending tech products."""
    queries = [
        "trending tech products this week 2026",
        "best selling gadgets Amazon electronics 2026",
        "viral tech gadgets TikTok 2026",
        "top tech products Pinterest trending",
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
        time.sleep(2)  # rate limit
    return products


def scrape_techradar_trending():
    """Fetch trending products from TechRadar."""
    url = "https://www.techradar.com/best/best-gadgets"
    html = fetch_url(url)
    if html.startswith("ERROR"):
        return []
    text = html_to_text(html)
    return extract_products_from_text(text, "techradar")


def scrape_verge_trending():
    """Fetch trending products from The Verge."""
    url = "https://www.theverge.com/tech"
    html = fetch_url(url)
    if html.startswith("ERROR"):
        return []
    text = html_to_text(html)
    return extract_products_from_text(text, "theverge")


def deduplicate_products(all_products):
    """Deduplicate by fuzzy matching on product names."""
    seen = set()
    unique = []
    for p in all_products:
        # Normalize for dedup
        key = re.sub(r'[^a-z0-9]', '', p["raw_text"].lower())[:50]
        if key not in seen and len(key) > 5:
            seen.add(key)
            unique.append(p)
    return unique


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    all_products = []
    sources_status = {}

    # Collect from all sources
    collectors = [
        ("reddit", scrape_reddit_gadgets),
        ("amazon", scrape_amazon_trending),
        ("google", scrape_google_trending_tech),
        ("techradar", scrape_techradar_trending),
        ("theverge", scrape_verge_trending),
        ("producthunt", scrape_product_hunt),
    ]

    for name, fn in collectors:
        try:
            results = fn()
            all_products.extend(results)
            sources_status[name] = {"count": len(results), "status": "ok"}
        except Exception as e:
            sources_status[name] = {"count": 0, "status": f"error: {e}"}

    # Deduplicate
    unique = deduplicate_products(all_products)

    # Build output
    output = {
        "date": today,
        "total_raw_mentions": len(all_products),
        "unique_products": len(unique),
        "sources": sources_status,
        "affiliate_tag": AFFILIATE_TAG,
        "categories": CATEGORIES,
        "products": unique[:60],  # top 60 for agent to curate down to 20
        "instructions": (
            "Above is raw product data scraped from multiple sources. "
            "Your job: select the TOP 20 most trending, pin-worthy tech products. "
            "For each, provide: name, description, why trending, price range, "
            "Amazon affiliate link (use /s?k= search format with tag=allitechstore-20), "
            "category, and a Pinterest pin caption idea. "
            "Generate the CSV and email it. Format the Telegram message as plain text."
        ),
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
