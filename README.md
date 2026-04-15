# Pinterest Tech Trends

Daily trending tech products scraper for the **SmartyPants9786** Pinterest board. Finds the top 20 trending electronics, gadgets, and tech products with Amazon Associates affiliate links, product images, and ready-to-post Pinterest pin files.

## What It Does

### Job 1: Trending Tech Products (every 6 hours) — 100% Python, no AI

1. **Scrapes** trending tech products from 6 sources:
   - Reddit (r/gadgets, r/technology, r/tech)
   - Amazon Best Sellers / Movers & Shakers
   - Google search results
   - TechRadar
   - The Verge
   - Product Hunt

2. **Curates** the top 20 by Reddit score + product filtering (no AI)

3. **Fetches 2 product images** per product from Amazon (1500px high-res)

4. **Generates** a CSV with product details, affiliate links, and image URLs

5. **Uploads** the CSV to Google Drive (PinterestAutomation folder)

6. **Emails** the CSV to your inbox with procured products tracking (NEW vs ALREADY PROCURED)

7. **Delivers** a formatted report to Telegram with procurement status indicators

**Cost: $0 per run** — entirely Python, no AI tokens used

### Job 2: Pinterest Pin Generator (30 min after Job 1) — 100% Python, no AI

1. **Polls** Google Drive for the latest CSV

2. **Checks** for already-pinned products (avoids duplicates)

3. **Creates** pin JSON files with title, description, hashtags, affiliate link, images, and alt text

4. **Uploads** pin files to Google Drive (PinterestAutomation/Pins folder)

5. **Delivers** a summary to Telegram

**Cost: $0 per run** — entirely Python, no AI tokens used

### Job 3: Pinterest Pin Uploader (4x daily: 1, 7, 13, 19) — CSV Import Content

1. **Scans** pending pin files and generates Pinterest-compatible CSV files

2. **Creates CSV** with format: Media, Board, Title, Description, Link, Alt text

3. **Processes up to 20 pins** per batch for efficient bulk upload

4. **Sends email** with CSV file location and manual upload instructions:
   - Go to https://business.pinterest.com/hub/
   - Click "Create" → "Bulk create Pins"  
   - Upload the CSV file
   - Review and publish

5. **Delivers** upload summary to Telegram

**Benefits**: Faster uploads, better rate limiting, more reliable than individual browser automation

**Cost: ~$0.08 per run** — no AI creativity, just mechanical browser clicks. 5 pins per batch with rate limiting.

**Note:** Uses Hermes browser tools (Browserbase) because Playwright headless doesn't work in WSL2 and Pinterest API trial access was denied. Can be converted to fully free Python if either becomes available.

## Project Layout

### GitHub Repo (source of truth)

```
~/pinterest-tech-trends/
├── .env.example                  Credential template
├── .gitignore                    Ignores secrets, caches, CSVs
├── README.md                     This file
├── ARCHITECTURE.md               Step-by-step breakdown with AI vs non-AI
├── MIGRATION.md                  Transfer to another computer
├── PROCURED_PRODUCTS_README.md  Documentation for procurement tracking
├── cron_job.json                 Job 1: scraper cron config
├── cron_job_pins.json            Job 2: pin generator cron config
├── cron_job_uploader.json        Job 3: pin uploader cron config
├── deploy.sh                     One-command deploy to Hermes
├── requirements.txt              Python dependencies
├── trending_tech_products.py     Scraper + image fetcher script
├── pinterest_pin_generator.py    Drive poller + pin file creator (100% Python)
├── pinterest_pin_uploader.py     CSV generator for Pinterest bulk upload
└── procured_products.json        List of already purchased products
```

Remote: https://github.com/Asif1924/pinterest-tech-trends

### Hermes (where it actually runs)

```
~/.hermes/
├── scripts/
│   ├── trending_tech_products.py    ← deployed scraper
│   ├── pinterest_pin_generator.py   ← deployed pin generator (100% Python)
│   ├── pinterest_pin_uploader.py    ← deployed uploader data collector
│   └── .venv/                       ← isolated Python environment
├── cron/
│   ├── jobs.json                    ← all 3 cron job definitions
│   └── output/
│       ├── e5acea7d6609/            ← Job 1 run logs
│       ├── acdacc6c6513/            ← Job 2 run logs
│       └── 17ff714ffd58/            ← Job 3 run logs
├── pinterest_pins/                  ← generated pin JSON files
├── .env                             ← credentials
└── config.yaml                      ← gateway config
```

### Google Drive

```
PinterestAutomation/
├── trending_tech_products_YYYY-MM-DD.csv   ← CSV with images
└── Pins/
    ├── pin_YYYYMMDD_01.json                ← pin files with images
    ├── pin_YYYYMMDD_02.json
    └── ...
```

### Flow

```
Job 1 (0 */6)               Job 2 (30 */6)              Job 3 (0 1,7,13,19)
AI — ~$0.20/run             Python — $0/run             Mechanical — ~$0.08/run
──────────────────          ──────────────────          ──────────────────────
Script scrapes sources      Script polls Drive          Script collects pin data
Agent curates top 20        Script creates pin JSONs    Agent logs into Pinterest
Agent fetches images        Script uploads to Drive     Agent uploads each pin
Agent generates CSV         Script outputs summary      Agent updates pin status
Agent uploads to Drive                                  
Agent emails CSV                                        
Agent sends Telegram                                    
```

## Setup

### Prerequisites

- [Hermes Agent](https://github.com/NousResearch/hermes-agent) installed and configured
- OpenRouter API key (for the AI agent)
- Gmail app password (for emailing the CSV)
- Telegram bot configured in Hermes (for report delivery)
- Google OAuth credentials with drive.file scope (for Drive uploads)
- Pinterest account credentials (for pin uploads)

## Features

### 🆕 Procured Products Tracking

The system now tracks which products you've already purchased to help avoid duplicates:

- **Email Separation**: Clearly shows NEW vs ALREADY PROCURED products
- **CSV Column**: Includes "Procured" column (Yes/No) for easy filtering
- **Smart Matching**: Partial name matching catches product variations
- **Priority Focus**: New products shown first in emails
- **Visual Indicators**: 🆕 for new products, ✓ for procured in reports

#### Managing Procured Products

Edit `procured_products.json` directly to add or remove products:

```json
{
  "procured": [
    "Apple AirPods Pro",
    "Samsung Galaxy Watch"
  ]
}
```

The system uses case-insensitive partial matching, so "Apple AirPods" will match variations like "Apple AirPods Pro 2nd Gen".

### Deploy

```bash
git clone https://github.com/Asif1924/pinterest-tech-trends.git
cd pinterest-tech-trends
cp .env.example .env
# Edit .env with your credentials
./deploy.sh
```

### Manual Run

```bash
# Test the scraper standalone
python3 trending_tech_products.py

# Trigger Job 1 (scraper + images + CSV)
hermes cron run e5acea7d6609

# Trigger Job 2 (pin generator — runs instantly, no AI)
hermes cron run acdacc6c6513

# Trigger Job 3 (pin uploader — browser automation)
hermes cron run 17ff714ffd58
```

## Making Changes

1. Edit scripts or cron configs in this repo
2. Run `./deploy.sh` to sync changes to Hermes
3. Push to GitHub: `git add -A && git commit -m "description" && git push`

## Schedule

- **Job 1:** Every 6 hours (12am, 6am, 12pm, 6pm)
- **Job 2:** 30 minutes after Job 1 (12:30am, 6:30am, 12:30pm, 6:30pm)
- **Job 3:** 1 hour after Job 1 (1am, 7am, 1pm, 7pm) — 5 pins per batch

## Pin JSON Format

Each pin file contains everything needed to post to Pinterest:

```json
{
  "product_name": "Dyson Handheld Fan",
  "board": "smartypants9786",
  "title": "Dyson Handheld Fan - $200-400",
  "description": "Stay cool anywhere with Dyson's game-changing handheld fan! #TechGadgets #CoolGadgets",
  "link": "https://www.amazon.com/s?k=Dyson+Handheld+Fan&tag=allitechstore-20",
  "category": "Cool Gadgets and Gizmos",
  "images": [
    {"url": "https://m.media-amazon.com/images/I/xxxxx._AC_SL1500_.jpg", "size": "large"},
    {"url": "https://m.media-amazon.com/images/I/yyyyy._AC_SL1500_.jpg", "size": "large"}
  ],
  "primary_image": "https://m.media-amazon.com/images/I/xxxxx._AC_SL1500_.jpg",
  "alt_text": "Product image of Dyson Handheld Fan",
  "price_range": "$200-400",
  "status": "pending_upload"
}
```

Status values: `pending_upload` → `uploaded` or `failed`

## Affiliate Tag

All Amazon links use the `allitechstore-20` associate tag. To change it, update `AFFILIATE_TAG` in `trending_tech_products.py`.

## Estimated Costs

- Job 1 (Python): $0 — free, no AI tokens
- Job 2 (Python): $0 — free, no AI tokens
- Job 3 (CSV generator): $0/run × 4/day = ~$0/month
- **Total: $0/month** — All jobs now run locally

Job 3 now uses CSV import → **Already $0/month!**



## License

MIT
