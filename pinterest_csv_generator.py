#!/home/asif/.hermes/hermes-agent/venv/bin/python
"""
Pinterest CSV Generator for Bulk Upload

Generates a Pinterest-compatible CSV file for bulk pin upload.
Pinterest CSV format requires: image_url, title, description, link, board_name
"""

import os
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

# Configuration
HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
INPUT_CSV = "/tmp/trending_tech_products.csv"
OUTPUT_CSV = "/home/asif/pinterest-tech-trends/pinterest_bulk_upload.csv"
BOARD_NAME = "SmartyPants9786"

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

def generate_pinterest_csv():
    """Convert our CSV to Pinterest bulk upload format"""
    
    products = []
    
    # Read the source CSV
    try:
        with open(INPUT_CSV, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("Product Name") and row.get("Image 1"):
                    products.append(row)
    except FileNotFoundError:
        print(f"ERROR: Source CSV not found at {INPUT_CSV}")
        return 0
    
    # Pinterest hashtags by category
    hashtags = {
        "Smart Home and IoT": "#SmartHome #IoT #HomeAutomation #TechHome #GadgetGoals",
        "Phone and Tablet Accessories": "#PhoneTech #MobileGadgets #SmartphoneAccessories",
        "Audio and Wearables": "#AudioTech #Wearables #Earbuds #SmartWatch",
        "Cool Gadgets and Gizmos": "#CoolGadgets #TechGadgets #GadgetLover #Innovation",
        "PC and Gaming Tech": "#GamingTech #PCGaming #GamingSetup #TechDeals"
    }
    
    # Write Pinterest CSV with EXACT column names Pinterest requires
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        # Pinterest EXACT required column names (case-sensitive!)
        fieldnames = ['Title', 'Description', 'Link', 'Image URL', 'Board']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for product in products[:100]:  # Pinterest allows up to 100 pins per CSV
            # Clean and format data
            title = product.get("Product Name", "").strip()[:100]
            if product.get("Price Range"):
                title = f"{title} - {product['Price Range']}"
            
            # Build description with hashtags
            category = product.get("Category", "Cool Gadgets and Gizmos")
            category_tags = hashtags.get(category, "#TechGadgets")
            description = product.get("Description", "").strip()[:400]
            description = f"{description} {category_tags}"
            
            # Write row in Pinterest's EXACT format
            writer.writerow({
                'Title': title,
                'Description': description,
                'Link': product.get("Amazon Link", ""),
                'Image URL': product.get("Image 1", ""),
                'Board': BOARD_NAME
            })
    
    return len(products)

def push_to_github():
    """Push the CSV to GitHub"""
    import subprocess
    
    repo_path = "/home/asif/pinterest-tech-trends"
    os.chdir(repo_path)
    
    try:
        subprocess.run("git add pinterest_bulk_upload.csv", shell=True, check=True)
        commit_date = datetime.now().strftime('%Y-%m-%d %H:%M')
        subprocess.run(f'git commit -m "Update Pinterest bulk upload CSV - {commit_date}"', 
                      shell=True, check=False)
        subprocess.run("git push", shell=True, check=True)
        return True
    except:
        return False

def main():
    """Main workflow"""
    send_telegram("📊 Pinterest CSV Generator started...")
    
    count = generate_pinterest_csv()
    
    if count > 0:
        push_to_github()
        
        msg = f"✅ Pinterest CSV ready with {count} products!\n"
        msg += f"📥 Download from: https://asif1924.github.io/pinterest-tech-trends/pinterest_bulk_upload.csv\n"
        msg += f"📌 Upload to Pinterest:\n"
        msg += f"1. Go to Settings → Import content\n"
        msg += f"2. Click 'Upload .csv or .txt'\n"
        msg += f"3. Upload the CSV file\n"
        msg += f"4. Review and publish pins"
        
        send_telegram(msg)
        print(msg)
    else:
        send_telegram("❌ Pinterest CSV generation failed - no products found")

if __name__ == "__main__":
    main()