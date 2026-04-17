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

# Firecrawl setup (API key loaded from .env, not config.json)
FIRECRAWL_CONFIG = CFG.get("firecrawl", {})
FIRECRAWL_API_KEY = ENV.get("FIRECRAWL_API_KEY", "")
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
    """Scrape Reddit r/gadgets using JSON API (no Firecrawl needed).

    Filters by post age to avoid long-running viral posts dominating results.
    Max age is configurable via config.scraping.reddit_max_age_hours (default 48h).
    """
    products = []
    max_age_hours = CFG.get("scraping", {}).get("reddit_max_age_hours", 48)
    cutoff_ts = time.time() - (max_age_hours * 3600)
    try:
        # Reddit provides JSON API, no need for Firecrawl
        url = "https://www.reddit.com/r/gadgets/hot.json?limit=50"
        result, method = scraper.scrape_smart(url, prefer_firecrawl=False)

        if "error" not in result:
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
    """Scrape Amazon Best Sellers, Movers & Shakers, and New Releases.

    Covers multiple categories and multiple list types for broader product
    discovery. Parses Firecrawl markdown by extracting the text of markdown
    links like [Product Name](amazon.com/dp/XXXX) — these are the actual
    product titles, not paragraph noise.

    Configurable via config.scraping.amazon:
      - categories: list of Amazon category slugs (default shown below)
      - list_types: list of list slugs ("zgbs"=bestsellers,
                    "movers-and-shakers"=trending up, "new-releases"=fresh)
      - per_source_limit: max products per single list page (default 20)
    """
    products = []
    cfg = CFG.get("scraping", {}).get("amazon", {})
    categories = cfg.get("categories", [
        "electronics", "computers", "wireless", "pc", "photo",
        "hpc", "kitchen", "home-garden", "toys-and-games", "officeproduct",
        "videogames", "hi",
    ])
    list_types = cfg.get("list_types", [
        ("zgbs", "bestsellers"),
        ("movers-and-shakers", "movers"),
        ("new-releases", "new"),
    ])
    per_source_limit = cfg.get("per_source_limit", 20)

    # Normalize list_types (JSON can't hold tuples — support list of 2-lists)
    list_types = [tuple(x) if isinstance(x, list) else x for x in list_types]

    # Budget within Amazon section so we don't starve later sources.
    amazon_budget = cfg.get("budget_seconds", 55)
    amazon_start = time.time()

    for list_slug, list_label in list_types:
        for cat in categories:
            if time.time() - amazon_start > amazon_budget:
                print(f"    (Amazon: budget {amazon_budget}s exceeded, stopping)")
                return products[:300]
            url = f"https://www.amazon.com/{list_slug}/{cat}"

            # Firecrawl required — Amazon blocks direct HTTP.
            result, method = scraper.scrape_smart(url, prefer_firecrawl=True)
            if "error" in result:
                continue

            content = ""
            if method == "firecrawl" and result.get("data"):
                content = result["data"].get("markdown", "")
            else:
                content = html_to_text(result.get("content", ""))

            if not content:
                continue

            # Primary pattern: markdown links to Amazon product pages.
            # Capture both the link TEXT and the ASIN so we can dedupe per product.
            link_matches = re.findall(
                r"\[([^\]]{2,200})\]\(https?://(?:www\.)?amazon\.com/[^)\s]*?(?:/dp/|/gp/product/)([A-Z0-9]{10})[^)]*\)",
                content,
            )

            # Amazon renders each product as multiple adjacent links (image link,
            # title link, price link) all pointing to the same ASIN. Group by
            # ASIN and pick the best candidate (longest alpha-heavy string).
            by_asin = {}
            for raw_name, asin in link_matches:
                name = re.sub(r"\s+", " ", raw_name).strip().strip("\\")
                by_asin.setdefault(asin, []).append(name)

            def is_price_like(s: str) -> bool:
                # Pure price strings: "$129.95 - $204.93", "$9.99", "$7-12"
                return bool(re.fullmatch(r"[\$\d\.,\-\s]+(?:\s*-\s*\$?[\d\.,]+)?", s))

            def looks_like_product(s: str) -> bool:
                if len(s) < 12 or len(s) > 160:
                    return False
                if is_price_like(s):
                    return False
                # Must have at least 3 word-characters worth of letters.
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
                return True

            added = 0
            seen_names = set()
            for asin, names in by_asin.items():
                # Pick the longest candidate that passes product heuristics.
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
                    "method": method,
                    "list_type": list_label,
                    "category": cat,
                    "asin": asin,
                    "url": f"https://www.amazon.com/dp/{asin}",
                })
                added += 1
                if added >= per_source_limit:
                    break

            if added:
                print(f"    Amazon {list_label}/{cat}: +{added} products")

    return products[:300]


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
def scrape_amazon_product_images(product_name, num_images=2, product_url=None):
    """Scrape Amazon product images.

    Strategy:
      1. If we have a direct /dp/ASIN URL (from the Amazon scraper), hit that
         product page — fastest and most reliable, gets the canonical hi-res image.
      2. Otherwise fall back to Amazon search by name.
    """
    images = []

    def _extract_from_markdown(md: str, limit: int):
        found = []
        patterns = [
            # Firecrawl-rendered markdown: ![alt](url)
            r'!\[[^\]]*\]\((https?://[^\s)]+\.(?:jpg|jpeg|png|webp))\)',
            # Amazon hi-res JSON field
            r'"hiRes":"(https?://[^"]+)"',
            # Common data attrs
            r'data-old-hires="(https?://[^"]+)"',
            r'data-a-dynamic-image="[^"]*(https?://[^"\s\\]+\.jpg)',
        ]
        for pat in patterns:
            for m in re.findall(pat, md):
                url = m if isinstance(m, str) else m[0]
                # Only keep actual product images (filter out icons/sprites)
                if any(x in url for x in ["/images/I/", "m.media-amazon.com/images/I/"]):
                    if url not in found:
                        found.append(url)
                        if len(found) >= limit:
                            return found
        return found

    # 1. Direct product page via /dp/ASIN
    if product_url and "/dp/" in product_url:
        try:
            result, method = scraper.scrape_smart(product_url, prefer_firecrawl=True)
            if "error" not in result:
                md = ((result.get("data") or {}).get("markdown", "")
                      if method == "firecrawl"
                      else result.get("content", ""))
                images = _extract_from_markdown(md, num_images)
                if images:
                    return images
        except Exception as e:
            print(f"    dp-page image fetch failed: {e}")

    # 2. Fallback: Firecrawl extract_products on search page
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

    # 3. Last-resort: plain HTML scrape of search results
    query = urllib.parse.quote_plus(product_name)
    url = f"https://www.amazon.com/s?k={query}"
    result, _ = scraper.scrape_smart(url, prefer_firecrawl=False)
    if "error" not in result:
        html = result.get("content", "")
        images = _extract_from_markdown(html, num_images)

    return images


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
    
    # Fetch images (wall-clock deadline; see fetch_images_for_products)
    print("  Fetching product images...")
    products = fetch_images_for_products(products, start_time=start_time, budget_seconds=20)

    # LLM enrichment — fills Category/Description/Why Trending/Price Range/Pin Caption
    products = llm_enrich_products(products, start_time=start_time)

    # Save CSV in the rich schema Job 2 (pinterest_pin_generator.py) expects.
    print(f"  Saving CSV to {CSV_PATH}")
    rich_fields = [
        "Number", "Product Name", "Category", "Description", "Why Trending",
        "Price Range", "Amazon Link", "Pin Caption Idea",
        "Image 1", "Image 2", "Procured",
        # Legacy/diagnostic columns retained for backward compat + debugging:
        "score", "sources", "method",
    ]
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
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
    
    # Trigger Job 2 (Pin Generator) synchronously — inherits parent env,
    # captures output, and surfaces errors back to Telegram. Previously used
    # a detached Popen which orphaned the child when the cron wrapper exited.
    print("  Triggering Job 2 (Pin Generator)...")
    script_path = os.path.join(os.path.dirname(__file__), "pinterest_pin_generator.py")
    job2_start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            timeout=TIMEOUT_JOB2,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
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