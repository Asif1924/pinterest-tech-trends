# Pinterest Tech Trends

Daily trending tech products scraper for the **smartypants9786** Pinterest board. Finds the top 20 trending electronics, gadgets, and tech products with Amazon Associates affiliate links.

## What It Does

1. **Scrapes** trending tech products from 6 sources:
   - Reddit (r/gadgets, r/technology, r/tech)
   - Amazon Best Sellers / Movers & Shakers
   - Google search results
   - TechRadar
   - The Verge
   - Product Hunt

2. **Curates** the top 20 most pin-worthy products using AI (via Hermes Agent)

3. **Generates** a CSV with product details and Amazon affiliate links

4. **Emails** the CSV to your inbox

5. **Delivers** a formatted report to Telegram

## Files

| File | Purpose |
|------|---------|
| `trending_tech_products.py` | Data collection script — scrapes all sources, outputs JSON |
| `cron_job.json` | Hermes Agent cron job config (schedule, prompt, delivery) |
| `deploy.sh` | Deploys/updates the script and cron job on any machine with Hermes |
| `.env.example` | Template for required environment variables |

## Setup

### Prerequisites

- [Hermes Agent](https://github.com/NousResearch/hermes-agent) installed and configured
- OpenRouter API key (for the AI agent)
- Gmail app password (for emailing the CSV)
- Telegram bot configured in Hermes (for report delivery)

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

# Trigger the cron job via Hermes
hermes cron run <job_id>
```

## Making Changes

1. Edit `trending_tech_products.py` to change scraping sources, product filters, or output format
2. Edit `cron_job.json` to change the schedule or AI prompt
3. Run `./deploy.sh` to sync changes to Hermes

The deploy script copies the updated files and refreshes the cron job.

## Schedule

Runs daily at **9:00 AM** (local time). Change the schedule in `cron_job.json`:

```
"schedule": "0 9 * * *"
```

## Affiliate Tag

All Amazon links use the `allitechstore-20` associate tag. To change it, update `AFFILIATE_TAG` in `trending_tech_products.py`.

## License

MIT
