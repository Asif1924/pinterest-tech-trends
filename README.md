# Pinterest Tech Trends

Daily trending tech products scraper for the **smartypants9786** Pinterest board. Finds the top 20 trending electronics, gadgets, and tech products with Amazon Associates affiliate links, product images, and ready-to-post Pinterest pin files.

## What It Does

### Job 1: Trending Tech Products (every 6 hours)

1. **Scrapes** trending tech products from 6 sources:
   - Reddit (r/gadgets, r/technology, r/tech)
   - Amazon Best Sellers / Movers & Shakers
   - Google search results
   - TechRadar
   - The Verge
   - Product Hunt

2. **Curates** the top 20 most pin-worthy products using AI

3. **Fetches 2 product images** per product from Amazon (1500px high-res)

4. **Generates** a CSV with product details, affiliate links, and image URLs

5. **Uploads** the CSV to Google Drive (PinterestAutomation folder)

6. **Emails** the CSV to your inbox

7. **Delivers** a formatted report to Telegram

### Job 2: Pinterest Pin Generator (30 min after Job 1)

1. **Polls** Google Drive for the latest CSV

2. **Checks** for already-pinned products (avoids duplicates)

3. **Creates** pin JSON files with title, description, hashtags, affiliate link, images, and alt text

4. **Uploads** pin files to Google Drive (PinterestAutomation/Pins folder)

5. **Delivers** a summary to Telegram

## Project Layout

### GitHub Repo (source of truth)

```
~/pinterest-tech-trends/
├── .env.example                  Credential template
├── .gitignore                    Ignores secrets, caches, CSVs
├── README.md                     This file
├── ARCHITECTURE.md               Step-by-step breakdown with AI vs non-AI
├── MIGRATION.md                  Transfer to another computer
├── cron_job.json                 Job 1: scraper cron config
├── cron_job_pins.json            Job 2: pin generator cron config
├── deploy.sh                     One-command deploy to Hermes
├── requirements.txt              Python dependencies
├── trending_tech_products.py     Scraper + image fetcher script
└── pinterest_pin_generator.py    Drive poller + CSV parser script
```

Remote: https://github.com/Asif1924/pinterest-tech-trends

### Hermes (where it actually runs)

```
~/.hermes/
├── scripts/
│   ├── trending_tech_products.py    ← deployed scraper
│   ├── pinterest_pin_generator.py   ← deployed pin generator
│   └── .venv/                       ← isolated Python environment
├── cron/
│   ├── jobs.json                    ← both cron job definitions
│   └── output/
│       ├── e5acea7d6609/            ← Job 1 run logs
│       └── acdacc6c6513/            ← Job 2 run logs
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
Job 1 (0 */6 * * *)                Job 2 (30 */6 * * *)
────────────────────                ────────────────────
Script scrapes 6 sources            Script polls Drive for CSV
Agent curates top 20                Agent creates pin JSON files
Agent fetches Amazon images         Agent uploads pins to Drive
CSV → Drive + Email + Telegram      Summary → Telegram
         │                                    │
         ▼                                    ▼
  PinterestAutomation/              PinterestAutomation/Pins/
  trending_tech_*.csv               pin_YYYYMMDD_NN.json
```

## Setup

### Prerequisites

- [Hermes Agent](https://github.com/NousResearch/hermes-agent) installed and configured
- OpenRouter API key (for the AI agent)
- Gmail app password (for emailing the CSV)
- Telegram bot configured in Hermes (for report delivery)
- Google OAuth credentials with drive.file scope (for Drive uploads)

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

# Trigger Job 2 (pin generator)
hermes cron run acdacc6c6513
```

## Making Changes

1. Edit scripts or cron configs in this repo
2. Run `./deploy.sh` to sync changes to Hermes
3. Push to GitHub: `git add -A && git commit -m "description" && git push`

## Schedule

- **Job 1:** Every 6 hours (12am, 6am, 12pm, 6pm)
- **Job 2:** 30 minutes after Job 1 (12:30am, 6:30am, 12:30pm, 6:30pm)

## Pin JSON Format

Each pin file contains everything needed to post to Pinterest:

```json
{
  "product_name": "Dyson Handheld Fan",
  "board": "smartypants9786",
  "title": "Short engaging title (max 100 chars)",
  "description": "Pin description with hashtags (max 500 chars)",
  "link": "https://www.amazon.com/s?k=Dyson+Handheld+Fan&tag=allitechstore-20",
  "category": "Cool Gadgets and Gizmos",
  "images": [
    {"url": "https://m.media-amazon.com/images/I/xxxxx._AC_SL1500_.jpg", "size": "large"},
    {"url": "https://m.media-amazon.com/images/I/yyyyy._AC_SL1500_.jpg", "size": "large"}
  ],
  "primary_image": "https://m.media-amazon.com/images/I/xxxxx._AC_SL1500_.jpg",
  "alt_text": "Accessibility description of the product image",
  "price_range": "$200-400",
  "status": "pending_upload"
}
```

## Affiliate Tag

All Amazon links use the `allitechstore-20` associate tag. To change it, update `AFFILIATE_TAG` in `trending_tech_products.py`.

## Estimated Costs

Using Claude Sonnet 4 on OpenRouter:
- Job 1: ~$0.15-0.25 per run
- Job 2: ~$0.10-0.15 per run
- Daily (4 runs each): ~$1.00-1.60
- Monthly: ~$30-50

## License

MIT
