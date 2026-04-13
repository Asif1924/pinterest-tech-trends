#!/home/asif/.hermes/hermes-agent/venv/bin/python
"""
Pinterest RSS Feed Generator

Reads the local CSV from Job 1 and generates an RSS feed for Pinterest.
Pinterest will automatically import pins from this RSS feed.
"""

import os
import csv
import json
import html
from datetime import datetime, timezone
from pathlib import Path

# Configuration
HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
CSV_PATH = "/tmp/trending_tech_products.csv"
RSS_PATH = "/tmp/pinterest_feed.xml"
GITHUB_REPO = "Asif1924/pinterest-tech-trends"
GITHUB_PAGES_URL = f"https://asif1924.github.io/pinterest-tech-trends"

def load_env_var(name):
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

def send_telegram(text):
    import urllib.request as _ur
    token = load_env_var("TELEGRAM_BOT_TOKEN")
    chat_id = load_env_var("TELEGRAM_HOME_CHANNEL")
    if not token or not chat_id:
        return
    try:
        data = json.dumps({"chat_id": chat_id, "text": text}).encode()
        req = _ur.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, headers={"Content-Type": "application/json"}
        )
        _ur.urlopen(req, timeout=10)
    except Exception:
        pass

def read_csv():
    """Read products from the CSV file"""
    products = []
    try:
        with open(CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Clean and validate the data
                if row.get("Product Name") and row.get("Amazon Link"):
                    products.append({
                        "title": html.escape(row.get("Product Name", "").strip()[:100]),
                        "description": html.escape(row.get("Description", "").strip()[:500]),
                        "link": html.escape(row.get("Amazon Link", "").strip()),
                        "image": row.get("Image 1", "").strip(),
                        "category": row.get("Category", "Tech").strip(),
                        "price": row.get("Price Range", "").strip()
                    })
    except FileNotFoundError:
        print(f"ERROR: CSV file not found at {CSV_PATH}")
        return []
    except Exception as e:
        print(f"ERROR reading CSV: {e}")
        return []
    
    return products

def generate_rss(products):
    """Generate RSS 2.0 feed compatible with Pinterest"""
    
    # RSS header
    rss_content = '''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" 
     xmlns:media="http://search.yahoo.com/mrss/"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
    <title>Tech Trends & Gadgets</title>
    <link>https://asif1924.github.io/pinterest-tech-trends/</link>
    <description>Latest trending tech products and gadgets with Amazon affiliate links</description>
    <language>en-us</language>
    <lastBuildDate>{last_build}</lastBuildDate>
    <ttl>360</ttl>
'''.format(last_build=datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"))
    
    # Add items
    for i, product in enumerate(products[:20], 1):  # Pinterest recommends max 20 items
        # Create item
        item_date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        
        # Build description with hashtags
        hashtags = {
            "Smart Home and IoT": "#SmartHome #IoT #HomeAutomation",
            "Phone and Tablet Accessories": "#PhoneTech #MobileGadgets",
            "Audio and Wearables": "#AudioTech #Wearables #Earbuds",
            "Cool Gadgets and Gizmos": "#CoolGadgets #TechGadgets #Innovation",
            "PC and Gaming Tech": "#GamingTech #PCGaming #TechDeals"
        }
        
        category_tags = hashtags.get(product["category"], "#TechGadgets")
        full_description = f"{product['description']} {category_tags}"
        
        # Add price to title if available
        title = product["title"]
        if product["price"]:
            title = f"{title} - {product['price']}"
        
        item_xml = f'''
    <item>
        <title>{title}</title>
        <link>{product["link"]}</link>
        <description>{full_description}</description>
        <pubDate>{item_date}</pubDate>
        <guid isPermaLink="false">tech-product-{datetime.now().strftime("%Y%m%d")}-{i:02d}</guid>'''
        
        # Add image if available (Pinterest requires this)
        if product["image"]:
            item_xml += f'''
        <media:content url="{html.escape(product['image'])}" type="image/jpeg">
            <media:title>{title}</media:title>
            <media:description>{product['description']}</media:description>
        </media:content>'''
        
        item_xml += '''
    </item>'''
        
        rss_content += item_xml
    
    # Close RSS
    rss_content += '''
</channel>
</rss>'''
    
    return rss_content

def save_rss(rss_content):
    """Save RSS to file"""
    try:
        with open(RSS_PATH, 'w', encoding='utf-8') as f:
            f.write(rss_content)
        return True
    except Exception as e:
        print(f"ERROR saving RSS: {e}")
        return False

def push_to_github():
    """Push the RSS file to GitHub Pages"""
    import subprocess
    
    repo_path = f"/home/asif/pinterest-tech-trends"
    
    # Ensure repo exists and is up to date
    if not os.path.exists(repo_path):
        print(f"ERROR: Repository not found at {repo_path}")
        return False
    
    try:
        # Copy RSS to repo
        subprocess.run(f"cp {RSS_PATH} {repo_path}/feed.xml", shell=True, check=True)
        
        # Git operations
        os.chdir(repo_path)
        subprocess.run("git add feed.xml", shell=True, check=True)
        commit_msg = f"Auto-update Pinterest RSS feed {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subprocess.run(f'git commit -m "{commit_msg}"', 
                      shell=True, check=False)  # Don't fail if nothing to commit
        subprocess.run("git push", shell=True, check=True)
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR pushing to GitHub: {e}")
        return False

def main():
    """Main workflow"""
    start_time = datetime.now(timezone.utc)
    
    send_telegram("📡 RSS Generator started: Creating Pinterest RSS feed...")
    
    # Read products from CSV
    products = read_csv()
    if not products:
        send_telegram("❌ RSS Generator failed: No products found in CSV")
        return
    
    print(f"Found {len(products)} products in CSV")
    
    # Generate RSS
    rss_content = generate_rss(products)
    
    # Save RSS
    if not save_rss(rss_content):
        send_telegram("❌ RSS Generator failed: Could not save RSS file")
        return
    
    print(f"RSS feed saved to {RSS_PATH}")
    
    # Push to GitHub
    if push_to_github():
        feed_url = f"{GITHUB_PAGES_URL}/feed.xml"
        success_msg = f"✅ RSS Generator complete: {len(products)} products in feed\n"
        success_msg += f"📍 Feed URL: {feed_url}\n"
        success_msg += f"⏰ Pinterest will auto-import within 24 hours"
        send_telegram(success_msg)
        print(success_msg)
    else:
        send_telegram("⚠️ RSS saved locally but GitHub push failed")
        print("Warning: GitHub push failed")

if __name__ == "__main__":
    main()