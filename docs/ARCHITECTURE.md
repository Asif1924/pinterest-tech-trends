# Architecture — Pinterest Tech Trends

The pipeline is three Python jobs chained as subprocesses. Job 1 is the only
job on a real cron schedule; Job 2 and Job 3 are launched by their parent and
inherit the same run id via `HERMES_PIPELINE_RUN_ID`. All artefacts for a
given execution land in a single atomic directory.

## Run Directory

```
~/.hermes/pinterest/
├── runs/
│   └── 2026-06-13T05-35-42Z/        ← run id (UTC ISO-8601, ':' → '-')
│       ├── 01_raw_products.csv      ← Job 1 output
│       ├── 02_pinterest_bulk.csv    ← Job 2 output / Job 3 input
│       ├── pins/
│       │   ├── pin_01.json          ← one per product, with images & affiliate link
│       │   └── pin_NN.json
│       ├── job3_zernio.log          ← per-pin Zernio MCP request/response
│       └── manifest.json            ← stage timings, statuses, counts
├── current  →  runs/2026-06-13T05-35-42Z   (symlink, swung atomically by Job 1)
└── archive/                                  (tar.gz of evicted runs)
```

Path resolution is centralised in `pipeline_paths.py`; manifest mutations go
through `pipeline_manifest.py`. Both modules are imported by all three jobs.

## Job Flow

```
cron  ──► Job 1 ──(subprocess)──► Job 2 ──(subprocess)──► Job 3
                                                            │
                                                            └── Zernio MCP
```

### Job 1 — `trending_tech_products.py`

| Step | What it does | Key artefacts |
| --- | --- | --- |
| 1 | Scrape Reddit, Amazon BSR/New, Google, TechRadar, The Verge, Product Hunt | (in-memory) |
| 2 | Curate top 20 (filter, dedupe, score by source weight) | (in-memory) |
| 3 | Fetch 2 high-res Amazon images per product | (in-memory) |
| 4 | Apply affiliate strategy (search-link or direct `/dp/ASIN`) | (in-memory) |
| 5 | Optional LLM enrichment (LM Studio / OpenAI-compatible) | (in-memory) |
| 6 | Create new run dir, write `01_raw_products.csv`, init manifest | `<run_dir>/01_raw_products.csv`, `manifest.json` |
| 7 | Swing `current` symlink atomically to the new run | `current → runs/<RUN_ID>` |
| 8 | Email CSV report + post Telegram summary | (SMTP, Telegram) |
| 9 | `subprocess.run` Job 2 with `HERMES_PIPELINE_RUN_ID` set | — |

### Job 2 — `pinterest_pin_generator.py`

| Step | What it does | Key artefacts |
| --- | --- | --- |
| 1 | Resolve run dir from `HERMES_PIPELINE_RUN_ID` or `current` symlink | — |
| 2 | Read `01_raw_products.csv`, skip rows where `procured = YES` | — |
| 3 | Build pin JSON per product and write to `pins/pin_NN.json` | `<run_dir>/pins/pin_NN.json` |
| 4 | Write Pinterest bulk-upload CSV (Media, Board, Title, Description, Link, Alt text) | `<run_dir>/02_pinterest_bulk.csv` |
| 5 | Enforce `quality_gates.min_pins` (default 3) — abort otherwise | — |
| 6 | Update manifest stage `job2` (counts, elapsed, status) | `manifest.json` |
| 7 | Email summary + post Telegram report | (SMTP, Telegram) |
| 8 | `subprocess.run` Job 3 with the same run id | — |

### Job 3 — `pinterest_pin_uploader.py`

| Step | What it does | Key artefacts |
| --- | --- | --- |
| 1 | Resolve run dir; refuse if neither env var nor `current` resolves | — |
| 2 | Read `02_pinterest_bulk.csv` | — |
| 3 | For each row, call Zernio MCP `create_pin` (`https://mcp.zernio.com/mcp`) | per-pin log line in `job3_zernio.log` |
| 4 | Capture per-pin request/response/status for diagnostics | `<run_dir>/job3_zernio.log` |
| 5 | Update each pin JSON's status to `uploaded` / `failed` | `<run_dir>/pins/pin_NN.json` |
| 6 | Update manifest stage `job3` (uploaded, failed, elapsed) | `manifest.json` |
| 7 | Post final Telegram summary | (Telegram) |

## Health & Retention — `pinterest_pipeline_health.py`

A utility script (not on cron yet) that:

- Archives runs older than `retention.archive_after_days` into `archive/<RUN_ID>.tar.gz`
- Deletes archives beyond `retention.keep_last_successful` / `keep_last_failed`
- Alerts (Telegram) on stale or repeatedly-failing runs

## Cron Configuration

| Config file | Schedule | Enabled |
| --- | --- | --- |
| `cron_job.json` | `0 * * * *` (every hour) | yes |
| `cron_job_pins.json` | `30 */6 * * *` | no — chained from Job 1 |
| `cron_job_uploader.json` | `0 1,7,13,19 * * *` | no — chained from Job 2 |

Job 2 and 3 keep cron entries for documentation / manual-trigger purposes.

## Cost

All three jobs run locally and make zero LLM calls in the hot path. The only
recurring cost is the Zernio MCP plan used to publish pins.

## Supporting Files

| File | Role |
| --- | --- |
| `deploy.sh` | Sync scripts + venv + cron configs from repo into `~/.hermes/` |
| `pipeline_paths.py` | Single source of truth for run-dir layout |
| `pipeline_manifest.py` | Atomic read/write of `manifest.json` |
| `pinterest_config.json` | Board name, quality gates, retention, timeouts, scoring |
| `procured_products.json` | Skip-list of already-purchased products |
