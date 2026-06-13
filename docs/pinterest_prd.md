# Product Requirements Document (PRD)

## Project: Pinterest Tech Trends Pipeline

## 1. Overview

The **Pinterest Tech Trends Pipeline** is a self-contained Python automation
that, on an hourly cron, discovers trending tech products, generates
Pinterest-ready pin assets with Amazon Associates affiliate links, and
publishes them to the **SmartyPants2786** board via the Zernio MCP.

The pipeline replaces what was historically a browser-automation workflow
(Selenium / Playwright Chromium). The current implementation publishes
through Zernio's MCP endpoint (`https://mcp.zernio.com/mcp`), removing the
fragile UI-driven login and CSV-import steps entirely.

## 2. Objectives

- Surface trending tech products without manual research
- Produce Pinterest-publish-ready pin JSONs (title, description, alt text,
  affiliate link, hi-res images) on every run
- Publish all eligible pins automatically with full per-pin diagnostics
- Maintain an auditable, per-run artefact directory for every execution
- Avoid duplicate pins via a procured-products skip-list

## 3. Target Users

- The repository owner (Asif1924) — sole production user
- Forks / clones used by other affiliate marketers running their own boards

## 4. Functional Requirements

| ID | Requirement |
| --- | --- |
| FR1 | Scrape Reddit, Amazon BSR/New, Google, TechRadar, The Verge, Product Hunt |
| FR2 | Curate top-N (default 20) products with source-weighted scoring |
| FR3 | Fetch two high-resolution Amazon images per product |
| FR4 | Apply configured affiliate-link strategy (search or `/dp/ASIN`) |
| FR5 | Skip products listed in `procured_products.json` |
| FR6 | Persist per-run artefacts under `~/.hermes/pinterest/runs/<RUN_ID>/` |
| FR7 | Maintain `current` symlink pointing at the latest successful run |
| FR8 | Generate Pinterest bulk-upload CSV from pin JSONs |
| FR9 | Publish each pin through the Zernio MCP `create_pin` tool |
| FR10 | Log per-pin Zernio request/response to `<run_dir>/job3_zernio.log` |
| FR11 | Enforce a `min_pins` quality gate before publishing |
| FR12 | Deliver email + Telegram summaries at each stage |
| FR13 | Archive runs older than `retention.archive_after_days` |
| FR14 | Read all secrets from `~/.hermes/.env`; never hard-code |

## 5. Non-Functional Requirements

- **Reliability:** Job 1 completes within `timeouts.job1_deadline` (default 480 s).
- **Observability:** Every stage writes structured entries to
  `manifest.json`; failures include stage, error class, and timestamp.
- **Idempotence:** Re-running Job 2 or Job 3 against an existing run dir
  overwrites cleanly without partial state.
- **Security:** Secrets live only in `~/.hermes/.env` (mode `0600`).
- **Portability:** All paths resolve via `pipeline_paths.py`; honouring
  `HERMES_HOME` makes the whole pipeline testable in isolation.

## 6. Technical Design

- Python 3.10+
- Standard library + `requests`, `python-dotenv`, optional Firecrawl client
- Zernio MCP (HTTP) for publishing — no browser automation
- Hermes Agent for cron scheduling and Telegram delivery
- LM Studio / OpenAI-compatible endpoint optional for product enrichment

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full per-stage breakdown.

## 7. Risks & Mitigations

| Risk | Mitigation |
| --- | --- |
| Source-site HTML changes | Per-source scraper isolated; failure of one source does not abort the run |
| Amazon image-CDN rate limits | Per-source budget + retry/backoff |
| Zernio MCP outage | Job 3 logs the error per pin, marks the run partial, alerts via Telegram |
| Pin duplication | `procured_products.json` skip-list + per-run manifest history |
| Disk growth | `pinterest_pipeline_health.py` archives + prunes old runs |

## 8. Out of Scope

- Pinterest analytics ingestion
- Multi-board support within a single run (one board per pipeline instance)
- Manual Pinterest UI login or CSV import (superseded by Zernio MCP)

## 9. Assumptions

- A valid Zernio MCP plan with `create_pin` permission
- A Gmail-compatible SMTP account for email reports
- A Telegram bot configured in Hermes for status delivery
- Hermes Agent installed and the gateway running
