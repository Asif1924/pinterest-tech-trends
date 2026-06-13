#!/usr/bin/env python3
"""
Trending Tech Products — SCRAPLING-FIRST SCRAPING (Firecrawl only as last resort)
Primary: Scrapling (StealthyFetcher anti-bot, DynamicFetcher JS rendering, adaptive selectors)
Fallback: Firecrawl (when quota available)
Fallback: urllib (simple/API endpoints)

Changes:
  - Scrapling as primary engine: local, no API costs, anti-bot bypass, adaptive selectors
  - StealthyFetcher for Amazon/product pages (Cloudflare handling)
  - DynamicFetcher (Playwright Chromium) for JS-heavy sites (ProductHunt, TechRadar, Verge)
  - Firecrawl only when scrapling fails AND quota available
  - urllib for Reddit JSON API (no JS needed)
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

# Import our Firecrawl hybrid client (kept as last-resort fallback)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from firecrawl_client import FirecrawlHybridClient
import pipeline_paths as paths
import pipeline_manifest as manifest

# ── Scrapling Integration ─────────────────────────────────────────────────────
# Scrapling fetchers: StealthyFetcher (anti-bot), DynamicFetcher (Playwright JS), Spiders
try:
    from scrapling.fetchers import StealthyFetcher, DynamicFetcher
    SCRAPLING_AVAILABLE = True
except ImportError:
    StealthyFetcher = DynamicFetcher = None
    SCRAPLING_AVAILABLE = False
    print("  ⚠️ Scrapling not installed — install with: pip install 'scrapling[fetchers]'")

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

# Firecrawl setup (API key loaded from .env, not config.json) — LAST RESORT ONLY
FIRECRAWL_CONFIG = CFG.get("firecrawl", {})
FIRECRAWL_API_KEY = ENV.get("FIRECRAWL_API_KEY", "")
FIRECRAWL_ENABLED = FIRECRAWL_CONFIG.get("enabled", False) and FIRECRAWL_API_KEY

# Initialize hybrid scraper (fallback only)
scraper = FirecrawlHybridClient(api_key=FIRECRAWL_API_KEY if FIRECRAWL_ENABLED else None)

# Existing config
TOP_N = CFG.get("top_n_products", 20)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT_HTTP = CFG.get("timeouts", {}).get("http_request", 15)
TIMEOUT_TELEGRAM = CFG.get("timeouts", {}).get("telegram_api", 10)
TIMEOUT_IMAGE = CFG.get("timeouts", {}).get("image_scrape", 15)
TIMEOUT_JOB2 = CFG.get("timeouts", {}).get("job2_subprocess", 120)

# LLM enrichment (LM Studio / OpenAI-compatible)
LLM_CFG = CFG.get("llm", {})
LLM_ENABLED = LLM_CFG.get("enabled", True)
LLM_BASE_URL = LLM_CFG.get("base_url", "http://192.168.1.7:1234/v1")
LLM_MODEL = LLM_CFG.get("model", "hermes-qwen3.5-35b-a3b")
LLM_TIMEOUT = LLM_CFG.get("timeout_seconds", 180)
LLM_API_KEY = LLM_CFG.get("api_key", ENV.get("LMSTUDIO_API_KEY", "lm-studio"))

# Links
LINK_STRATEGY = CFG.get("link_strategy", 2)
AFFILIATE_TAG = CFG.get("affiliate_tag", "allitechstore-20")


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


# ── Scrapling Helper: Unified fetch with fallback chain ──────────────────────
def _scrapling_fetch(url, prefer_dynamic=False, timeout=30000):
    """
    Fetch URL using Scrapling with fallback chain:
    1. StealthyFetcher (anti-bot, Cloudflare bypass) for product pages
    2. DynamicFetcher (Playwright Chromium) for JS-heavy pages
    3. Firecrawl (if enabled and quota available)
    4. urllib (plain HTTP)
    
    Returns: (content_dict, method_name) where content_dict has 'content' (html), 'markdown' (text), 'success' keys
    """
    # 1. StealthyFetcher — anti-bot, good for Amazon/product pages
    if SCRAPLING_AVAILABLE and StealthyFetcher:
        try:
            StealthyFetcher.adaptive = True
            page = StealthyFetcher.fetch(
                url, headless=True, network_idle=True,
                block_images=False, block_fonts=True, block_media=True,
                timeout=timeout,
            )
            if page and page.status == 200:
                # Get text content
                markdown = page.get_all_text() if hasattr(page, 'get_all_text') else ''
                if not markdown:
                    # Collect text from body elements
                    body_els = page.css('body')
                    if body_els:
                        markdown = ' '.join(el.get_all_text() for el in body_els if el.get_all_text())
                return {"content": page.html_content, "markdown": markdown, "success": True}, "stealthyfetcher"
        except Exception as e:
            print(f"    [stealthyfetcher] failed for {url}: {e}")
    
    # 2. DynamicFetcher — Playwright/Chromium for JS-heavy pages
    if SCRAPLING_AVAILABLE and DynamicFetcher and prefer_dynamic:
        try:
            DynamicFetcher.adaptive = True
            page = DynamicFetcher.fetch(
                url, headless=True, network_idle=True,
                block_images=True, block_fonts=True, browser_type="chromium",
            )
            if page and page.status == 200:
                markdown = page.get_all_text() if hasattr(page, 'get_all_text') else ''
                if not markdown:
                    body_els = page.css('body')
                    if body_els:
                        markdown = ' '.join(el.get_all_text() for el in body_els if el.get_all_text())
                return {"content": page.html_content, "markdown": markdown, "success": True}, "dynamicfetcher"
        except Exception as e:
            print(f"    [dynamicfetcher] failed for {url}: {e}")
    
    # 3. Firecrawl — last resort if enabled and has quota
    if scraper.has_firecrawl:
        try:
            result = scraper._make_firecrawl_request('/scrape', {
                'url': url,
                'pageOptions': {'waitFor': 3000},
            })
            if result.get('success') and not result.get('error'):
                return {"content": result.get('data', {}).get('markdown', ''), 
                        "markdown": result.get('data', {}).get('markdown', ''), 
                        "success": True}, "firecrawl"
        except Exception as e:
            print(f"    [firecrawl] failed for {url}: {e}")
    
    # 4. urllib fallback — plain HTTP
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT_HTTP) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
        return {"content": html, "markdown": html_to_text(html), "success": True}, "urllib"
    except Exception as e:
        print(f"    [urllib] failed for {url}: {e}")
        return {"content": "", "markdown": "", "success": False, "error": str(e)}, "failed"


# ── Text Extraction (kept for urllib fallback) ─────────────────────────────
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
    """Scrape Reddit r/gadgets using JSON API (no Scrapling/Firecrawl needed).

    Filters by post age to avoid long-running viral posts dominating results.
    Max age is configurable via config.scraping.reddit_max_age_hours (default 48h).
    """
    products = []
    max_age_hours = CFG.get("scraping", {}).get("reddit_max_age_hours", 48)
    cutoff_ts = time.time() - (max_age_hours * 3600)
    try:
        # Reddit provides JSON API, no need for Scrapling/Firecrawl
        url = "https://www.reddit.com/r/gadgets/hot.json?limit=50"
        result, method = _scrapling_fetch(url, prefer_dynamic=False)
        if result.get("success"):
            data = json.loads(result.get("content", "{}"))
            skipped_old = 0
            for post in data.get("data", {}).get("children", []):
                p = post.get("data", {})
                created = p.get("created_utc", 0)
                if created and created < cutoff_ts:
                    skipped_old += 1
                    continue
                products.append({
                    "name": p.get("title", ""),
                    "score": p.get("score", 0),
                    "url": p.get("url", ""),
                    "comments": p.get("num_comments", 0),
                    "source": "reddit",
                    "created_utc": created,
                })
            if skipped_old:
                print(f"    (Reddit: skipped {skipped_old} posts older than {max_age_hours}h)")
    except Exception as e:
        send_telegram(f"⚠️ Reddit scrape error: {str(e)[:100]}")

    return products


def scrape_amazon_trending():
    """Scrape Amazon Best Sellers, Movers & Shakers, and New Releases using Scrapling CSS selectors.

    Primary: StealthyFetcher (anti-bot) for Amazon list pages + CSS extraction
    Fallback: Firecrawl (if quota available)
    Fallback: urllib

    Configurable via config.scraping.amazon:
      - categories: list of Amazon category slugs
      - list_types: list of list slugs ("zgbs"=bestsellers, "movers-and-shakers"=trending up, "new-releases"=fresh)
      - per_source_limit: max products per single list page (default 20)
    """
    products = []
    cfg = CFG.get("scraping", {}).get("amazon", {})
    categories = cfg.get("categories", [
        "toys-and-games",
    ])
    list_types = cfg.get("list_types", [
        ("zgbs", "bestsellers"),
        ("new-releases", "new"),
    ])
    per_source_limit = cfg.get("per_source_limit", 20)
    amazon_domain = cfg.get("domain", "com")

    list_types = [tuple(x) if isinstance(x, list) else x for x in list_types]

    amazon_budget = cfg.get("budget_seconds", 55)
    amazon_start = time.time()

    # Import Scrapling fetchers directly for CSS access
    if not SCRAPLING_AVAILABLE or not StealthyFetcher:
        print("    (Amazon: Scrapling not available)")
        return products

    StealthyFetcher.adaptive = True

    # Best sellers URL category name mapping (Amazon uses title-case in URL)
    # Amazon.ca uses 'toys' as category slug (not 'toys-and-games')
    bestseller_category_names = {
        "toys": "Toys-Games",
    }

    for list_slug, list_label in list_types:
        for cat in categories:
            if time.time() - amazon_start > amazon_budget:
                print(f"    (Amazon: budget {amazon_budget}s exceeded, stopping)")
                return products[:300]
            
            # Build correct Amazon URL based on list type
            if list_slug == "zgbs":
                display_name = bestseller_category_names.get(cat, cat.title().replace("-", " "))
                url = f"https://www.amazon.{amazon_domain}/Best-Sellers-{display_name}/{list_slug}/{cat}"
            else:
                url = f"https://www.amazon.{amazon_domain}/{list_slug}/{cat}"

            # Scrapling fetcher — use StealthyFetcher for bestsellers, DynamicFetcher for new-releases
            try:
                if list_slug == "zgbs":
                    page = StealthyFetcher.fetch(
                        url, headless=True, network_idle=True,
                        disable_resources=True,
                        timeout=amazon_budget * 1000,
                    )
                else:  # new-releases
                    page = DynamicFetcher.fetch(
                        url, headless=True,
                        network_idle=True,
                        timeout=amazon_budget * 1000,
                    )
                if not page or page.status != 200:
                    print(f"    Amazon {list_label}/{cat}: status {page.status if page else 'None'}")
                    continue
                
                # Extract product links using CSS selectors based on page type
                def is_price_like(s: str) -> bool:
                    return bool(re.fullmatch(r"[\$\d\.,\-\s]+(?:\s*-\s*\$?[\d\.,]+)?", s))

                def looks_like_product(s: str) -> bool:
                    if len(s) < 12 or len(s) > 160:
                        return False
                    if is_price_like(s):
                        return False
                    letters = sum(c.isalpha() for c in s)
                    if letters < 10:
                        return False
                    low = s.lower()
                    if any(skip in low for skip in [
                        "see more", "shop now", "learn more", "view all",
                        "sign in", "add to cart", "delivering to",
                        "customer review", "amazon basics", "main content",
                        "hello,", "cart", "returns&", "orders",
                    ]):
                        return False
                    # Filter out non-product links
                    if any(skip in low for skip in [
                        "amazon business card", "reload your balance", "gift card",
                        "prime video", "prime music", "prime reading", "kindle",
                        "audible", "amazon music", "amazon photos", "amazon drive",
                        "amazon web services", "aws", "amazon pay", "amazonbasics",
                        "monthly auto-renewal", "auto-renewal", "subscription plan",
                        "blink plus plan",
                    ]):
                        return False
                    return True

                by_asin = {}

                # Different selector strategies per list type
                # Both bestsellers (zgbs) and new-releases use .zg-grid-general-faceout grid
                product_cells = page.css('.zg-grid-general-faceout')
                for cell in product_cells:
                    # Title is in a.a-link-normal.aok-block - pick the one with actual text
                    title_links = cell.css('a.a-link-normal.aok-block[href*="/dp/"]')
                    for el in title_links:
                        href = el.attrib.get('href', '')
                        text = el.get_all_text().strip() if hasattr(el, 'get_all_text') else ''
                        if text and href and len(text) > 15:  # skip empty image links
                            asin_match = re.search(r'/dp/([A-Z0-9]{10})', href)
                            if asin_match:
                                asin = asin_match.group(1)
                                by_asin.setdefault(asin, []).append(text)
                                break  # take first one with real text

                added = 0
                seen_names = set()
                for asin, names in by_asin.items():
                    candidates = [n for n in names if looks_like_product(n)]
                    if not candidates:
                        continue
                    name = max(candidates, key=len)
                    key = name.lower()[:60]
                    if key in seen_names:
                        continue
                    seen_names.add(key)
                    products.append({
                        "name": name,
                        "source": f"amazon_{list_label}_{cat}",
                        "method": "stealthyfetcher_css",
                        "list_type": list_label,
                        "category": cat,
                        "asin": asin,
                        "url": f"https://www.amazon.{amazon_domain}/dp/{asin}",
                    })
                    added += 1
                    if added >= per_source_limit:
                        break

                if added:
                    print(f"    Amazon {list_label}/{cat}: +{added} products [stealthyfetcher_css]")

            except Exception as e:
                print(f"    [stealthyfetcher] failed for {url}: {e}")

    return products[:300]

def scrape_google_trending_tech():
    """Scrape Google search results using Scrapling DynamicFetcher (JS-rendered)."""
    products = []
    queries = ["trending tech gadgets 2024", "new technology products", "cool gadgets"]
    
    for query in queries:
        url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}&num=15"
        
        # DynamicFetcher for JS-rendered search results
        result, method = _scrapling_fetch(url, prefer_dynamic=True)
        if not result.get("success"):
            continue
            
        text = result.get("markdown", "") or html_to_text(result.get("content", ""))
        # Extract product names from search results
        for match in re.findall(r'[A-Z][A-Za-z0-9\s\-]+(?:Pro|Plus|Max|Mini)?', text):
            if 10 < len(match) < 60:
                products.append({
                    "name": match.strip(),
                    "source": "google_search",
                    "method": method
                })
    
    return products


def scrape_techradar():
    """Scrape TechRadar using Scrapling DynamicFetcher (JS-heavy site)."""
    products = []
    url = "https://www.techradar.com/best/best-gadgets"
    
    # DynamicFetcher for JS-heavy TechRadar
    result, method = _scrapling_fetch(url, prefer_dynamic=True)
    
    if not result.get("success"):
        return products
    
    content = result.get("markdown", "") or html_to_text(result.get("content", ""))
    for line in content.split("\n"):
        if any(keyword in line.lower() for keyword in ["best", "top", "great", "excellent"]):
            matches = re.findall(r'(?:The\s+)?([A-Z][A-Za-z0-9\s\-]+(?:Pro|Plus|Max|Mini|Ultra)?)', line)
            for match in matches:
                if 10 < len(match) < 80:
                    products.append({
                        "name": match.strip(),
                        "source": "techradar",
                        "method": method
                    })
    
    return products


def scrape_verge():
    """Scrape The Verge using Scrapling DynamicFetcher (JS-heavy site)."""
    url = "https://www.theverge.com/tech"
    result, method = _scrapling_fetch(url, prefer_dynamic=True)
    
    products = []
    if not result.get("success"):
        return products
    
    content = result.get("markdown", "") or html_to_text(result.get("content", ""))
    products.extend(extract_product_names(content, "theverge", method))
    
    return products


def scrape_producthunt():
    """Scrape Product Hunt using Scrapling DynamicFetcher (JS-heavy, infinite scroll)."""
    url = "https://www.producthunt.com/feed"
    result, method = _scrapling_fetch(url, prefer_dynamic=True)
    
    products = []
    if not result.get("success"):
        return products
    
    content = result.get("markdown", "") or html_to_text(result.get("content", ""))
    lines = content.split("\n")
    for line in lines:
        if not line.startswith("#") and len(line) > 5:
            clean = re.sub(r'\[.*?\]|\(.*?\)', '', line).strip()
            if 5 < len(clean) < 80:
                products.append({
                    "name": clean,
                    "source": "producthunt",
                    "method": method
                })
    
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
    cfg = CFG.get("scraping", {}).get("amazon", {})
    amazon_domain = cfg.get("domain", "com")
    terms = urllib.parse.quote_plus(product_name)
    return f"https://www.amazon.{amazon_domain}/s?k={terms}&tag={tag}"


def affiliate_link_strategy_2(product_name, affiliate_tag=None):
    """Strategy 2: Direct Product Links using Firecrawl."""
    tag = affiliate_tag or AFFILIATE_TAG
    cfg = CFG.get("scraping", {}).get("amazon", {})
    amazon_domain = cfg.get("domain", "com")
    
    # Try Firecrawl first for better extraction
    if scraper.has_firecrawl:
        query = urllib.parse.quote_plus(product_name)
        url = f"https://www.amazon.{amazon_domain}/s?k={query}"
        
        # Use Firecrawl's extract feature for product data
        products = scraper.extract_products(url)
        if products and len(products) > 0:
            # Get first product's link
            product_link = products[0].get("link", "")
            # Extract ASIN from link
            asin_match = re.search(r'/dp/([A-Z0-9]{10})', product_link)
            if asin_match:
                asin = asin_match.group(1)
                return f"https://www.amazon.{amazon_domain}/dp/{asin}?tag={tag}"
    
    # Fallback to original method
    query = urllib.parse.quote_plus(product_name)
    url = f"https://www.amazon.{amazon_domain}/s?k={query}"
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
                return f"https://www.amazon.{amazon_domain}/dp/{asin}?tag={tag}"
    
    # Fallback to search link
    return affiliate_link_strategy_1(product_name, affiliate_tag)


# ── Image Scraping with Scrapling ─────────────────────────────────────────────
def scrape_amazon_product_images(product_name, num_images=2, product_url=None):
    """Scrape Amazon product images using Scrapling (fast, adaptive, anti-bot).

    Strategy:
      1. If we have a direct /dp/ASIN URL, hit that product page with StealthyFetcher
         (anti-bot bypass, Cloudflare handling) + adaptive selectors.
      2. Fallback to Amazon search by name with DynamicFetcher for JS-rendered results.
      3. Last resort: Firecrawl extract_products (existing fallback).
    """
    images = []

    # 1. Direct product page via /dp/ASIN using Scrapling StealthyFetcher
    if product_url and "/dp/" in product_url:
        try:
            from scrapling.fetchers import StealthyFetcher
            StealthyFetcher.adaptive = True
            page = StealthyFetcher.fetch(
                product_url,
                headless=True,
                network_idle=True,
                block_images=False,  # Need images to extract their URLs
                block_fonts=True,
                block_media=True,
                timeout=30000,
            )
            if page and page.status == 200:
                # Extract image URLs using adaptive CSS selectors
                # Amazon product images typically in #landingImage, #imgTagWrapperId, or .a-dynamic-image
                img_selectors = [
                    '#landingImage',
                    '#imgTagWrapperId img',
                    '.a-dynamic-image',
                    '[data-old-hires]',
                    '.a-button-thumbnail img',
                ]
                for selector in img_selectors:
                    elements = page.css(selector, adaptive=True, auto_save=True)
                    for el in elements:
                        # Try multiple attributes for the image URL
                        for attr in ['src', 'data-old-hires', 'data-a-dynamic-image', 'data-src']:
                            url = el.attrib.get(attr, '')
                            if url and url.startswith('http') and any(ext in url for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                                # Clean up data-a-dynamic-image JSON
                                if attr == 'data-a-dynamic-image':
                                    import json
                                    try:
                                        urls = json.loads(url)
                                        for u in urls.keys():
                                            if u not in images and 'media-amazon.com/images/I/' in u:
                                                images.append(u)
                                                if len(images) >= num_images:
                                                    return images[:num_images]
                                    except:
                                        pass
                                elif 'media-amazon.com/images/I/' in url:
                                    if url not in images:
                                        images.append(url)
                                        if len(images) >= num_images:
                                            return images[:num_images]
                if images:
                    return images[:num_images]
        except Exception as e:
            print(f"    [scrapling] dp-page image fetch failed: {e}")

    # 2. Fallback: Amazon search with DynamicFetcher (JS rendering for search results)
    try:
        query = urllib.parse.quote_plus(product_name)
        url = f"https://www.amazon.com/s?k={query}"
        from scrapling.fetchers import DynamicFetcher
        DynamicFetcher.adaptive = True
        page = DynamicFetcher.fetch(
            url,
            headless=True,
            network_idle=True,
            block_images=False,
            block_fonts=True,
            browser_type="chromium",
        )
        if page and page.status == 200:
            # Search result images
            elements = page.css('.s-image, .a-dynamic-image', adaptive=True, auto_save=True)
            for el in elements:
                src = el.attrib.get('src', '')
                if src and src.startswith('http') and 'media-amazon.com/images/I/' in src:
                    if src not in images:
                        images.append(src)
                        if len(images) >= num_images:
                            return images[:num_images]
            if images:
                return images[:num_images]
    except Exception as e:
        print(f"    [scrapling] search image fetch failed: {e}")

    # 3. Last resort: Firecrawl extract_products (existing fallback)
    if scraper.has_firecrawl:
        try:
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
        except Exception:
            pass

    # 4. Plain HTML scrape of search results (final fallback)
    query = urllib.parse.quote_plus(product_name)
    url = f"https://www.amazon.com/s?k={query}"
    result, _ = scraper.scrape_smart(url, prefer_firecrawl=False)
    if "error" not in result:
        html = result.get("content", "")
        # Reuse existing extraction patterns
        patterns = [
            r'"hiRes":"(https?://[^"]+)"',
            r'data-old-hires="(https?://[^"]+)"',
            r'data-a-dynamic-image="[^"]*(https?://[^"\s\\]+?\.jpg)',
        ]
        for pat in patterns:
            for m in re.findall(pat, html):
                url = m if isinstance(m, str) else m[0]
                if 'media-amazon.com/images/I/' in url and url not in images:
                    images.append(url)
                    if len(images) >= num_images:
                        return images

    return images[:num_images] if images else []


def fetch_images_for_products(products, start_time=None, budget_seconds=30):
    """Fetch images for all products, with a wall-clock budget.

    If start_time is provided, stop fetching when elapsed exceeds the image-fetch
    deadline. Products without images get an empty list.
    """
    skipped = 0
    skip_mode = False
    # Absolute wall-clock deadline (seconds since start_time) for image fetching.
    # Job 1 subprocess cap is ~480s; we reserve ~240s for LLM enrichment + email +
    # Job 2/3 chain. Override via config: timeouts.image_fetch_deadline.
    image_deadline = CFG.get("timeouts", {}).get("image_fetch_deadline", 240)
    for idx, p in enumerate(products):
        if start_time is not None:
            elapsed = time.time() - start_time
            if elapsed > image_deadline:
                if not skip_mode:
                    print(f"  ⏱️ Image-fetch deadline ({image_deadline}s) exceeded at product {idx}/{len(products)} — skipping rest")
                skip_mode = True
                skipped += 1
                p["images"] = []
                continue
        try:
            images = scrape_amazon_product_images(
                p["name"],
                num_images=2,
                product_url=p.get("url"),
            )
        except Exception as e:
            print(f"    ⚠️ image fetch failed for {p.get('name','?')[:40]}: {e}")
            images = []
        p["images"] = images
    if skipped:
        print(f"  (skipped {skipped} products' images to stay within budget)")
    return products


# ── LLM Enrichment (LM Studio) ──────────────────────────────────────────────
def _llm_chat(messages, max_tokens=3500, temperature=0.4, timeout=None):
    """Call an OpenAI-compatible chat completion endpoint (LM Studio).

    Returns the content string, or None on failure.
    """
    url = LLM_BASE_URL.rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or LLM_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  ⚠️ LLM call failed: {e}")
        return None


def _parse_json_block(text):
    """Extract a JSON array/object from an LLM response (handles ``` fences)."""
    if not text:
        return None
    # Strip ```json ... ``` or ``` ... ``` fences
    m = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    candidate = m.group(1) if m else text
    # Find the outermost [ ... ] or { ... }
    for opener, closer in (("[", "]"), ("{", "}")):
        i = candidate.find(opener)
        j = candidate.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(candidate[i:j + 1])
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(candidate)
    except Exception:
        return None


def _fallback_enrichment(name):
    """Cheap deterministic enrichment used when LLM is unavailable."""
    return {
        "category": "Tech Gadget",
        "description": f"{name} — a trending tech product getting attention across Reddit, Amazon, ProductHunt and tech review sites.",
        "why_trending": "Buzz across multiple tech communities and shopping sources this week.",
        "price_range": "$50 - $300",
        "pin_caption": f"🔥 {name} is trending — check it out! #tech #gadgets #trending",
    }


def llm_enrich_products(products, start_time=None):
    """Enrich each product with category/description/price/caption via LLM.

    Single batched JSON request for efficiency. Falls back to deterministic text
    on any failure so the pipeline never blocks.
    """
    if not products:
        return products
    if not LLM_ENABLED:
        print("  ℹ️ LLM enrichment disabled in config — using fallback text.")
        for p in products:
            p.update(_fallback_enrichment(p["name"]))
        return products

    # Respect wall-clock budget. Job 1's total runtime budget (pre-Job-2) is
    # configurable via timeouts.job1_deadline (default 300s). Past that, skip LLM.
    if start_time is not None:
        elapsed = time.time() - start_time
        job1_deadline = CFG.get("timeouts", {}).get("job1_deadline", 300)
        remaining = job1_deadline - elapsed
        if remaining < 30:
            print(f"  ⏱️ Not enough time for LLM ({remaining:.0f}s left before Job 1 deadline) — using fallback text.")
            for p in products:
                p.update(_fallback_enrichment(p["name"]))
            return products

    print(f"  🧠 Enriching {len(products)} products via LLM ({LLM_MODEL})...")
    product_list = [{"i": i, "name": p["name"], "sources": list(set(p.get("sources", [])))}
                    for i, p in enumerate(products)]

    system = (
        "You write concise, upbeat Pinterest product descriptions for trending tech gadgets. "
        "Always respond with ONLY a valid JSON array, no prose, no markdown fences."
    )
    user = (
        "For each product below, return a JSON array where each item has exactly these keys: "
        "i (integer, matching input), category (string, 2-4 words), "
        "description (string, 1-2 sentences, 120-200 chars, no emoji), "
        "why_trending (string, 1 sentence, 80-140 chars), "
        "price_range (string, e.g. \"$50 - $150\"), "
        "pin_caption (string, 80-160 chars, may include 1-2 emojis and 2-4 hashtags).\n\n"
        "Products:\n" + json.dumps(product_list, ensure_ascii=False)
    )

    llm_start = time.time()
    content = _llm_chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=4000,
        temperature=0.5,
    )
    llm_elapsed = time.time() - llm_start
    print(f"  🧠 LLM responded in {llm_elapsed:.1f}s")

    parsed = _parse_json_block(content) if content else None
    if not isinstance(parsed, list):
        print("  ⚠️ LLM returned unparseable response — using fallback text.")
        for p in products:
            p.update(_fallback_enrichment(p["name"]))
        return products

    # Map by index
    by_idx = {}
    for item in parsed:
        if isinstance(item, dict) and "i" in item:
            try:
                by_idx[int(item["i"])] = item
            except (TypeError, ValueError):
                continue

    filled = 0
    for i, p in enumerate(products):
        item = by_idx.get(i) or {}
        fb = _fallback_enrichment(p["name"])
        p["category"] = (item.get("category") or fb["category"]).strip()
        p["description"] = (item.get("description") or fb["description"]).strip()
        p["why_trending"] = (item.get("why_trending") or fb["why_trending"]).strip()
        p["price_range"] = (item.get("price_range") or fb["price_range"]).strip()
        p["pin_caption"] = (item.get("pin_caption") or fb["pin_caption"]).strip()
        if i in by_idx:
            filled += 1
    print(f"  ✅ Enriched {filled}/{len(products)} from LLM ({len(products) - filled} fallback).")
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
    
    # Per-source scraping with a global wall-clock budget.
    # Script runner kills us at 120s; reserve ~30s for scoring/CSV/email/telegram/Job2 dispatch.
    SCRAPE_BUDGET_SECONDS = CFG.get("timeouts", {}).get("scrape_budget", 85)
    for source_name, scrape_func in sources:
        elapsed_so_far = time.time() - start_time
        if elapsed_so_far > SCRAPE_BUDGET_SECONDS:
            print(f"  ⏱️ Skipping {source_name} — scrape budget ({SCRAPE_BUDGET_SECONDS}s) exceeded (elapsed {elapsed_so_far:.1f}s)")
            send_telegram(f"⏱️ Skipped {source_name} — budget exceeded")
            continue
        print(f"  Scraping {source_name}... (elapsed {elapsed_so_far:.1f}s)")
        try:
            products = scrape_func()
            all_products.extend(products)
            print(f"    Found {len(products)} products")
        except Exception as e:
            print(f"    Error: {e}")
            send_telegram(f"⚠️ {source_name} scrape failed: {str(e)[:100]}")
    
    # Score and rank products.
    # Weights are configurable; defaults favor Amazon Movers & Shakers (rising
    # best-sellers = strongest real-world trend signal) and penalize generic
    # Reddit post noise that relies purely on upvote counts.
    weights = CFG.get("scoring", {}).get("source_weights", {
        "amazon_movers":       2.5,
        "amazon_new":          1.8,
        "amazon_bestsellers":  1.5,
        "amazon":              1.2,   # fallback for unknown amazon sublabel
        "producthunt":         1.3,
        "theverge":            0.9,
        "techradar":           0.9,
        "google":              0.7,
        "reddit":              0.6,
    })

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
                "method": p.get("method", "unknown"),
                "url": p.get("url", ""),
            }
        # Prefer an Amazon /dp/ URL if we see one later for the same product
        if not product_scores[name_key].get("url") and p.get("url"):
            product_scores[name_key]["url"] = p["url"]
        elif "/dp/" in (p.get("url") or "") and "/dp/" not in product_scores[name_key].get("url", ""):
            product_scores[name_key]["url"] = p["url"]

        # Determine source-family weight (handles amazon_movers_electronics etc.)
        src = p.get("source", "unknown")
        weight = 1.0
        if src.startswith("amazon_movers"):
            weight = weights.get("amazon_movers", 2.5)
        elif src.startswith("amazon_new"):
            weight = weights.get("amazon_new", 1.8)
        elif src.startswith("amazon_bestsellers"):
            weight = weights.get("amazon_bestsellers", 1.5)
        elif src.startswith("amazon"):
            weight = weights.get("amazon", 1.2)
        else:
            weight = weights.get(src, 1.0)

        product_scores[name_key]["score"] += weight
        product_scores[name_key]["sources"].append(src)

        if src == "reddit":
            product_scores[name_key]["reddit_score"] = p.get("score", 0)
            # Cap reddit upvote contribution so one viral post doesn't dominate
            product_scores[name_key]["score"] += min(p.get("score", 0) / 100, 5.0)
    
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
    
    
    # LLM enrichment — fills Category/Description/Why Trending/Price Range/Pin Caption
    products = llm_enrich_products(products, start_time=start_time)

    # Create a fresh per-run directory and write the raw CSV into it.
    # All downstream stages resolve this path via HERMES_PIPELINE_RUN_ID
    # or the `current` symlink.
    run_dir = paths.new_run_dir()
    run_csv = run_dir / paths.RAW_CSV_NAME
    paths.set_current(run_dir)
    manifest.init(run_dir)
    print(f"  Run id: {paths.run_id_of(run_dir)}")
    print(f"  Saving CSV to {run_csv}")
    rich_fields = [
        "Number", "Product Name", "Category", "Description", "Why Trending",
        "Price Range", "Amazon Link", "Pin Caption Idea",
        "Image 1", "Image 2", "Procured",
        # Legacy/diagnostic columns retained for backward compat + debugging:
        "score", "sources", "method",
    ]
    with open(run_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rich_fields)
        writer.writeheader()
        for i, p in enumerate(products, 1):
            imgs = p.get("images", []) or []
            writer.writerow({
                "Number": i,
                "Product Name": p["name"],
                "Category": p.get("category", ""),
                "Description": p.get("description", ""),
                "Why Trending": p.get("why_trending", ""),
                "Price Range": p.get("price_range", ""),
                "Amazon Link": p["link"],
                "Pin Caption Idea": p.get("pin_caption", ""),
                "Image 1": imgs[0] if len(imgs) > 0 else "",
                "Image 2": imgs[1] if len(imgs) > 1 else "",
                "Procured": "YES" if p.get("procured") else "NO",
                "score": round(p["score"], 2),
                "sources": ",".join(set(p["sources"])),
                "method": p.get("method", "unknown"),
            })

    manifest.set_stage(run_dir, "job1", {
        "scraped": len(products),
        "csv": str(run_csv),
        "elapsed_s": round(time.time() - start_time, 2),
    })

    # Send email report
    send_email_report(products, run_csv)
    
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
    
    # Trigger Job 2 (Pin Generator) synchronously — inherits parent env,
    # captures output, and surfaces errors back to Telegram. Previously used
    # a detached Popen which orphaned the child when the cron wrapper exited.
    print("  Triggering Job 2 (Pin Generator)...")
    script_path = os.path.join(os.path.dirname(__file__), "pinterest_pin_generator.py")
    job2_start = time.time()
    job2_env = os.environ.copy()
    job2_env[paths.RUN_ID_ENV] = paths.run_id_of(run_dir)
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            timeout=TIMEOUT_JOB2,
            capture_output=True,
            text=True,
            env=job2_env,
            cwd=os.path.dirname(__file__),
        )
        job2_elapsed = time.time() - job2_start
        if result.stdout:
            print("  --- Job 2 stdout ---")
            print(result.stdout)
        if result.stderr:
            print("  --- Job 2 stderr ---")
            print(result.stderr)
        if result.returncode == 0:
            print(f"  ✅ Job 2 completed successfully in {job2_elapsed:.1f}s")
            send_telegram(
                f"✅ <b>Job 2 Complete:</b> Pinterest pins generated "
                f"({job2_elapsed:.1f}s)"
            )
        else:
            tail = (result.stderr or result.stdout or "")[-400:]
            print(f"  ❌ Job 2 exit code {result.returncode}")
            send_telegram(
                f"❌ <b>Job 2 failed</b> (exit {result.returncode})\n"
                f"<pre>{tail}</pre>"
            )
    except subprocess.TimeoutExpired:
        print(f"  ⚠️ Job 2 timed out after {TIMEOUT_JOB2}s")
        send_telegram(f"⚠️ Job 2 timed out after {TIMEOUT_JOB2}s")
    except Exception as e:
        print(f"  ❌ Job 2 failed: {e}")
        send_telegram(f"❌ Job 2 failed: {str(e)[:200]}")

    print("✅ Pipeline complete!")
    send_telegram("✅ <b>Pipeline Complete!</b> All jobs finished.")


def send_email_report(products, csv_path):
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
        
        # Attach CSV (canonical copy lives in the run dir)
        with open(csv_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment; filename=trending_tech_products.csv")
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