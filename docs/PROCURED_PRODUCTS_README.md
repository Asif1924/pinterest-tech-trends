# Procured Products Tracking

Job 1 (`trending_tech_products.py`) and Job 2 (`pinterest_pin_generator.py`)
consult a skip-list so already-purchased items are flagged in reports and
excluded from pin generation.

## How It Works

- Job 1 tags every product row with a `Procured` column (`YES`/`NO`) in
  `01_raw_products.csv`. Both the email and Telegram summaries split the top
  20 into "New" vs "Already procured".
- Job 2 reads the same CSV and *skips* rows where `Procured = YES`, so no pin
  JSON is generated and the bulk-upload CSV never references them.

## Managing the List

Edit `procured_products.json` at the repo root (deployed to
`~/.hermes/scripts/procured_products.json`):

```json
{
  "procured": [
    "Apple AirPods Pro",
    "Samsung Galaxy Watch",
    "Dyson V15 Detect"
  ]
}
```

Run `./deploy.sh` to push changes to Hermes, or edit the deployed copy
directly for one-off changes.

## Matching Logic

Matching is **case-insensitive** and **substring-based**. An entry of
`"Apple AirPods"` matches every product whose normalised name contains
`"apple airpods"`, including:

- `Apple AirPods Pro`
- `Apple AirPods Pro 2nd Gen`
- `Refurbished Apple AirPods`

Keep entries short and generic to catch variants; lengthen them only when you
need to exclude one specific SKU but keep its siblings.

## CSV Format

`01_raw_products.csv` has the following columns:

```
Number, Product Name, Category, Description, Why Trending,
Price Range, Amazon Link, Pin Caption Idea, Image 1, Image 2,
Procured, score, sources, method
```

`Procured` is `YES` if the product matched the skip-list, `NO` otherwise.

## Email Summary

```
Total: 20 products | New: 15 | Already Procured: 5
============================================================

🆕 NEW PRODUCTS TO CONSIDER (15):
1. Dyson V15 Detect Vacuum
   Category: Smart Home
   Why Trending: Reddit r/gadgets (1,234 upvotes)
2. Sony WH-1000XM5 Headphones
   …

✓ ALREADY PROCURED (5):
  • Apple AirPods Pro (Audio)
  • Samsung Galaxy Watch 6 (Wearables)
  …
```

## Related Files

- `trending_tech_products.py` — applies the skip-list during scraping
- `pinterest_pin_generator.py` — excludes procured rows when building pins
- `procured_products.json` — the skip-list itself
- `pinterest_config.json` — broader pipeline config (board name, gates, etc.)