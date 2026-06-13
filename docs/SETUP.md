# Setup Guide — Fresh Installation

This guide brings up the Pinterest Tech Trends pipeline on a new machine
with a fresh Hermes Agent installation.

## Prerequisites

- **Hermes Agent** installed and running — <https://github.com/NousResearch/hermes-agent>
- **Python 3.10+** with `venv` support
- **Git**
- Accounts / API keys per Step 2 below

## Step 1: Clone the Repository

```bash
git clone https://github.com/Asif1924/pinterest-tech-trends.git ~/pinterest-tech-trends
cd ~/pinterest-tech-trends
ls -la         # should show deploy.sh, cron_job*.json, *.py, .env.example, docs/
```

## Step 2: Gather API Keys & Credentials

### 2a. Firecrawl API Key (required)

Used by Job 1 to enrich scrapes that fail plain-`requests` fetches.

1. Sign up at <https://www.firecrawl.dev/>
2. Copy the API key from the dashboard

### 2b. Gmail App Password (required)

Used by Job 1 and Job 2 to email reports.

1. Enable 2-Step Verification: <https://myaccount.google.com/security>
2. Generate an App Password: <https://myaccount.google.com/apppasswords>
3. Save the 16-character password

### 2c. Telegram Bot & User ID (required)

1. Talk to **@BotFather** → `/newbot` → save the bot token
2. Talk to **@userinfobot** → save your numeric user ID

### 2d. Zernio MCP API Key (required for Job 3)

Job 3 publishes pins through the Zernio MCP. Sign up at
<https://zernio.com/>, provision an API key, and confirm the board
`SmartyPants2786` (or whatever you set in `pinterest_config.json`) is
visible to that account.

### 2e. LLM Endpoint (optional)

Optional enrichment (category, description, pin caption). Any
OpenAI-compatible endpoint works:

- **LM Studio** (local, free): <https://lmstudio.ai/> — note the base URL,
  e.g. `http://localhost:1234/v1`
- **Nous Research / OpenRouter**: set `LLM_API_KEY` and adjust `llm.base_url`
  + `llm.model` in `pinterest_config.json`

Disable entirely by setting `"llm": {"enabled": false}`.

## Step 3: Create the `.env` File

Secrets live in `~/.hermes/.env` (outside the repo, so they never enter git).

```bash
cp .env.example ~/.hermes/.env
chmod 600 ~/.hermes/.env
nano ~/.hermes/.env
```

Required fields:

```
FIRECRAWL_API_KEY=fc-...
EMAIL_ADDRESS=you@gmail.com
EMAIL_PASSWORD=xxxx xxxx xxxx xxxx
TELEGRAM_BOT_TOKEN=123456789:ABC...
TELEGRAM_HOME_CHANNEL=1234567890
ZERNIO_API_KEY=zer-...
```

Optional:

```
LLM_API_KEY=...                 # only if llm.enabled = true and the endpoint requires a key
HERMES_HOME=/custom/path        # override the default ~/.hermes for testing
```

## Step 4: Run the Deploy Script

```bash
cd ~/pinterest-tech-trends
./deploy.sh
```

`deploy.sh`:

1. Copies the four pipeline scripts (`trending_tech_products.py`,
   `pinterest_pin_generator.py`, `pinterest_pin_uploader.py`,
   `pinterest_pipeline_health.py`) plus their shared modules
   (`pipeline_paths.py`, `pipeline_manifest.py`) and config files
   (`pinterest_config.json`, `procured_products.json`) into
   `~/.hermes/scripts/`.
2. Creates `~/.hermes/scripts/.venv` and installs `requirements.txt`.
3. Refreshes Hermes cron entries from `cron_job.json`, `cron_job_pins.json`,
   and `cron_job_uploader.json`.
4. Verifies the deployed entry point imports cleanly.

If deployment fails:

```bash
hermes --version          # Hermes installed?
python3 --version         # Python 3.10+?
python3 -m venv --help    # venv module present?
ls -la ~/.hermes/         # Hermes home exists?
```

## Step 5: Verify Cron Registration

Only Job 1 should be enabled. Job 2 and Job 3 ride along as subprocesses.

```bash
hermes cron list
```

Expected:

| Job name | Schedule | Enabled |
| --- | --- | --- |
| Trending Tech Products for Pinterest | `0 * * * *` | yes |
| Pinterest Pin Generator | `30 */6 * * *` | no |
| Pinterest Pin Uploader | `0 1,7,13,19 * * *` | no |

If a job is missing, re-run `./deploy.sh`. If they're missing *after* a
deploy, create them manually (`hermes cron create --name … --schedule … --script …`).

## Step 6: Smoke Test

Run Job 1 on demand; Job 2 and Job 3 chain automatically:

```bash
hermes cron run "$(hermes cron list | awk '/Trending Tech Products/ {print $1; exit}')"
```

Then inspect the new run:

```bash
RUN_DIR=$(readlink -f ~/.hermes/pinterest/current)
ls "$RUN_DIR"
cat "$RUN_DIR/manifest.json"
tail -50 "$RUN_DIR/job3_zernio.log"
```

You should see `01_raw_products.csv`, `02_pinterest_bulk.csv`, a populated
`pins/` directory, `job3_zernio.log`, and a `manifest.json` showing
`job1.status`, `job2.status`, and `job3.status` all `ok` (or `partial` if
Zernio rate-limited individual pins).

Telegram should receive three messages (one per stage) and your inbox two
emails (Job 1's CSV report and Job 2's summary).

## Step 7: Replaying an Existing Run

To re-run Job 2 or Job 3 against the latest run without re-scraping:

```bash
export HERMES_PIPELINE_RUN_ID=$(basename "$(readlink ~/.hermes/pinterest/current)")
~/.hermes/scripts/.venv/bin/python ~/.hermes/scripts/pinterest_pin_generator.py
~/.hermes/scripts/.venv/bin/python ~/.hermes/scripts/pinterest_pin_uploader.py
```

Unset `HERMES_PIPELINE_RUN_ID` afterwards to avoid surprising the next cron-driven Job 1.

## Troubleshooting

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| `ERROR: Hermes home not found` | Hermes not installed | Install Hermes first |
| `FIRECRAWL_API_KEY not set` | `.env` missing or in the wrong place | Put it at `~/.hermes/.env`, mode 600 |
| Script not found in venv | Deploy aborted mid-flight | `rm -rf ~/.hermes/scripts/.venv && ./deploy.sh` |
| No Telegram messages | Wrong `TELEGRAM_HOME_CHANNEL` (must be numeric) or gateway down | `hermes gateway status` |
| Job 2 aborts with `quality gate failed` | Scraper returned fewer than `quality_gates.min_pins` products | Lower the gate or wait for the next hourly run |
| Job 3 every pin fails | Zernio key invalid or board name typo | Verify `ZERNIO_API_KEY`; check `pinterest.board_name` in `pinterest_config.json` |
| Empty `pins/` directory | All scraped products matched `procured_products.json` | Trim the skip-list |

## Next Steps

- Adjust `procured_products.json` after each purchase
- Tune `pinterest_config.json` (`top_n_products`, `scoring.source_weights`,
  `retention.*`, `timeouts.*`)
- Wire `pinterest_pipeline_health.py` into cron once you're ready for
  automated retention/alerting (no preset cron entry today)
- Back up `~/.hermes/.env`, `~/.hermes/cron/jobs.json`, and
  `~/.hermes/pinterest/` — see [MIGRATION.md](MIGRATION.md)

## See Also

- [README.md](README.md) — high-level overview
- [ARCHITECTURE.md](ARCHITECTURE.md) — per-stage breakdown
- [MIGRATION.md](MIGRATION.md) — moving Hermes between machines
- [PROCURED_PRODUCTS_README.md](PROCURED_PRODUCTS_README.md) — skip-list mechanics
