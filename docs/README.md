# Pinterest Tech Trends

Hourly trending-tech-products pipeline that posts to the **SmartyPants2786** Pinterest
board. Scrapes the top trending electronics, gadgets, and tech products, builds
Pinterest-ready pin JSONs with Amazon Associates affiliate links, and publishes
them via the Zernio MCP — all without leaving your machine.

> **New to this repo?** See [SETUP.md](SETUP.md) for fresh-install instructions.
> Architecture deep-dive: [ARCHITECTURE.md](ARCHITECTURE.md).
> Moving machines: [MIGRATION.md](MIGRATION.md).

## What It Does

The pipeline is three Python scripts chained together. Job 1 starts on a cron
schedule; each job exec's the next as a subprocess and passes the run id
through `HERMES_PIPELINE_RUN_ID` so all stages write into the same per-run
directory.

### Job 1 — `trending_tech_products.py` (every hour)

1. Scrapes Reddit, Amazon Best Sellers, Google, TechRadar, The Verge, Product Hunt
2. Curates the top 20 by Reddit score + product filtering
3. Fetches 2 high-res Amazon images per product
4. Optional LLM enrichment (LM Studio or OpenAI-compatible) for category /
   description / pin caption
5. Writes `01_raw_products.csv` into the run directory
6. Emails the CSV report and posts a Telegram summary
7. Chains Job 2

### Job 2 — `pinterest_pin_generator.py` (chained from Job 1)

1. Reads `<run_dir>/01_raw_products.csv`
2. Skips already-procured products (`procured_products.json`)
3. Writes one pin JSON per product to `<run_dir>/pins/pin_NN.json`
4. Writes the Pinterest bulk-upload CSV to `<run_dir>/02_pinterest_bulk.csv`
5. Enforces the `min_pins` quality gate (default 3); aborts otherwise
6. Emails the report and chains Job 3

### Job 3 — `pinterest_pin_uploader.py` (chained from Job 2)

1. Reads `<run_dir>/02_pinterest_bulk.csv`
2. POSTs each pin to Pinterest via the Zernio MCP (`https://mcp.zernio.com/mcp`)
3. Writes per-pin request / response detail to `<run_dir>/job3_zernio.log`
4. Updates the run manifest with success/partial/failed
5. Posts a Telegram summary

A separate utility, `pinterest_pipeline_health.py`, enforces retention
(archives older runs as `.tar.gz`) and alerts on stale or failed runs.

## Run-Directory Layout

Every execution writes into its own atomic directory. `current` always
points to the most recent run.

```
~/.hermes/pinterest/
├── runs/
│   └── 2026-06-13T05-35-42Z/
│       ├── 01_raw_products.csv      ← Job 1 output
│       ├── 02_pinterest_bulk.csv    ← Job 2 output, Job 3 input
│       ├── pins/
│       │   ├── pin_01.json
│       │   └── pin_NN.json
│       ├── job3_zernio.log          ← per-pin Zernio I/O
│       └── manifest.json            ← stage timings + status
├── current -> runs/2026-06-13T05-35-42Z   (symlink, updated atomically by Job 1)
└── archive/                                (tar.gz of evicted runs)
```

The run id flows Job 1 → Job 2 → Job 3 via `HERMES_PIPELINE_RUN_ID`; when
unset (manual reruns) jobs fall back to the `current` symlink. Jobs 2 and 3
refuse to run if neither is resolvable.

## Repository Layout

```
~/pinterest-tech-trends/
├── .env.example                  Credential template
├── .gitignore
├── deploy.sh                     One-command deploy to Hermes
├── requirements.txt
├── trending_tech_products.py     Job 1: scraper + image fetcher + enricher
├── pinterest_pin_generator.py    Job 2: pin JSON + bulk CSV generator
├── pinterest_pin_uploader.py     Job 3: Zernio MCP uploader
├── pipeline_paths.py             Single source of truth for run-dir paths
├── pipeline_manifest.py          Per-run manifest helpers
├── pinterest_pipeline_health.py  Retention + stale-run alerter
├── pinterest_config.json         Board name, quality gates, retention, paths
├── procured_products.json        Products already purchased (skip list)
├── cron_job.json                 Job 1 cron config (Job 2/3 chained)
├── cron_job_pins.json
├── cron_job_uploader.json
└── docs/
    ├── README.md                 You are here
    ├── ARCHITECTURE.md
    ├── SETUP.md
    ├── MIGRATION.md
    ├── PROCURED_PRODUCTS_README.md
    ├── SKILL.md
    └── pinterest_prd.md
```

Remote: <https://github.com/Asif1924/pinterest-tech-trends>

## Deploy & Run

```bash
git clone https://github.com/Asif1924/pinterest-tech-trends.git ~/pinterest-tech-trends
cd ~/pinterest-tech-trends
cp .env.example ~/.hermes/.env       # then edit with real values
./deploy.sh
```

Manual single-shot:

```bash
# Full pipeline (Job 1 chains 2 → 3 automatically)
python3 ~/.hermes/scripts/trending_tech_products.py

# Replay Job 2 against the latest run
HERMES_PIPELINE_RUN_ID=$(basename $(readlink ~/.hermes/pinterest/current)) \
  python3 ~/.hermes/scripts/pinterest_pin_generator.py

# Replay Job 3 against the latest run
HERMES_PIPELINE_RUN_ID=$(basename $(readlink ~/.hermes/pinterest/current)) \
  python3 ~/.hermes/scripts/pinterest_pin_uploader.py
```

## Schedule

| Job | Schedule | Notes |
| --- | --- | --- |
| Job 1 | `0 * * * *` (every hour) | Enabled; sole pipeline entry point |
| Job 2 | `30 */6 * * *` | `enabled: false` — chained from Job 1 |
| Job 3 | `0 1,7,13,19 * * *` | `enabled: false` — chained from Job 2 |

## Pin JSON Format

```json
{
  "product_name": "Dyson Handheld Fan",
  "board": "SmartyPants2786",
  "title": "Dyson Handheld Fan - $200-400",
  "description": "Stay cool anywhere with Dyson's game-changing handheld fan! #TechGadgets #CoolGadgets",
  "link": "https://www.amazon.com/s?k=Dyson+Handheld+Fan&tag=allitechstore-20",
  "category": "Cool Gadgets and Gizmos",
  "images": [{"url": "https://m.media-amazon.com/images/I/xxxxx._AC_SL1500_.jpg", "size": "large"}],
  "primary_image": "https://m.media-amazon.com/images/I/xxxxx._AC_SL1500_.jpg",
  "alt_text": "Product image of Dyson Handheld Fan",
  "price_range": "$200-400",
  "procured": false,
  "created_at": "2026-06-13T05:35:42+00:00",
  "status": "ready_for_upload"
}
```

## Procured-Products Tracking

`procured_products.json` is a simple skip-list. The scraper does
case-insensitive partial matching, so `"Apple AirPods"` matches
`"Apple AirPods Pro 2nd Gen"`. See [PROCURED_PRODUCTS_README.md](PROCURED_PRODUCTS_README.md)
for the full schema and email-format details.

## Affiliate Tag

All Amazon links use the `allitechstore-20` associate tag. Override via
`affiliate_tag` in `pinterest_config.json`.

## Costs

All three jobs are free at the script level (no LLM calls in the hot path).
The only paid dependency is the Zernio MCP plan you use to publish pins.

## License

MIT
