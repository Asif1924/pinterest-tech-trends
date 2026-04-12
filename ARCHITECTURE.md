# Architecture — Pinterest Tech Trends

```
Step  Description                  AI?   What does it                              Files
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

JOB 1: Trending Tech Products (every 6 hours) — 100% PYTHON, NO AI ($0/run)

1     Script scrapes 6 websites    No    Pure Python, urllib. Hits Reddit,          ~/.hermes/scripts/trending_tech_products.py
                                         Amazon, Google, TechRadar, The Verge,      ~/pinterest-tech-trends/trending_tech_products.py (source)
                                         Product Hunt. Sends Telegram start msg.

2     Script curates top 20        No    Filters for actual products (not news).    (same script)
                                         Ranks by Reddit score. Auto-categorizes
                                         by keyword matching. Extracts clean
                                         product names. Generates descriptions,
                                         hashtags, and pin captions from templates.

3     Script fetches product imgs  No    Calls scrape_amazon_product_images()       (same script)
                                         for each product. Gets 2 high-res Amazon
                                         images per product (1500px via CDN).

4     Script generates CSV         No    Writes CSV with columns: Number, Name,     /tmp/trending_tech_products.csv
                                         Category, Description, Why Trending,
                                         Price, Amazon Link, Caption, Image 1/2.

5     Script uploads CSV to Drive  No    Uses Google Drive API. Authenticates       ~/.hermes/google_token.json
                                         with OAuth, refreshes if expired.           Google Drive: PinterestAutomation/

6     Script emails CSV            No    smtplib SMTP to Gmail. Attaches CSV,       ~/.hermes/.env (EMAIL_PASSWORD)
                                         includes trend summary and Drive link.

7     Script outputs Telegram msg  No    Formats plain text report by category.     stdout → Hermes → Telegram
                                         Sends progress notifications throughout.

8     Hermes delivers to Telegram  No    Relays script stdout to Telegram chat.     ~/.hermes/.env (BOT_TOKEN)

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

JOB 2: Pinterest Pin Generator (runs 30 min after Job 1) — 100% PYTHON, NO AI ($0/run)

9     Script cleans old pins       No    Deletes all old local pin files and        ~/.hermes/pinterest_pins/
                                         old pin JSONs from Drive Pins folder.       Google Drive: PinterestAutomation/Pins/
                                         Deletes old CSVs (keeps latest 1).

10    Script polls Google Drive    No    Downloads latest CSV from                  ~/.hermes/scripts/pinterest_pin_generator.py
                                         PinterestAutomation folder via Drive API.

11    Script creates pin files     No    Generates pin JSON for each product:       ~/.hermes/pinterest_pins/pin_YYYYMMDD_NN.json
                                         title, description, hashtags, affiliate
                                         link, images, primary_image, alt text.

12    Script uploads pins to Drive No    Uploads each pin JSON to                   Google Drive: PinterestAutomation/Pins/
                                         PinterestAutomation/Pins folder.

13    Script outputs summary       No    Prints cleanup + creation report.          stdout → Hermes → Telegram

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

JOB 3: Pinterest Pin Uploader (runs 1 hour after Job 2) — MECHANICAL BROWSER AUTOMATION

14    Script collects pin data     No    Scans pending pin files, reads creds,      ~/.hermes/scripts/pinterest_pin_uploader.py
                                         batches pins (max 5), sends Telegram
                                         start notification.

15    Agent executes browser steps min   Mechanical only: log in, navigate to       ~/.hermes/.env (PINTEREST_EMAIL/PASSWORD)
                                         pin builder, upload image, fill fields,     ~/.hermes/pinterest_pins/pin_YYYYMMDD_NN.json
                                         click Publish. Same steps every pin.
                                         Sends ⏳/✅/❌ Telegram per pin.

16    Agent updates pin status     min   Changes "pending_upload" → "uploaded"       (same agent turn as step 15)
                                         or "failed". Deletes uploaded pin JSON
                                         from Google Drive.

17    Hermes delivers summary      No    Sends final batch summary to Telegram.

      NOTE: Job 3 still uses an agent turn for browser automation because
      Playwright headless doesn't work in WSL2 and Pinterest API trial was
      denied. If either becomes available, this job can go fully Python.

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

SUPPORTING FILES

      Deploy script                No    Copies scripts, creates venv, updates       ~/pinterest-tech-trends/deploy.sh
                                         cron jobs from repo to Hermes.

      GitHub repo                  No    Source of truth for all editable files.     ~/pinterest-tech-trends/
                                                                                     github.com/Asif1924/pinterest-tech-trends

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

SUMMARY: What uses AI tokens vs what's free

  FREE (no AI) — 14 of 17 steps:       AGENT (minimal tokens) — 3 of 17 steps:
  ─────────────────────────────         ─────────────────────────────
  Steps 1-8:   Job 1 (all Python)       Step 15: Browser clicks (mechanical)
  Steps 9-13:  Job 2 (all Python)       Step 16: Update status + delete from Drive
  Step 14:     Job 3 data collection    Step 17: Deliver summary
  Deploy, GitHub, cron scheduling

  Job 1: ZERO cost — 100% Python
  Job 2: ZERO cost — 100% Python
  Job 3: ~$0.08/run — mechanical browser automation only

MONTHLY COST ESTIMATE (4 runs/day):
  Job 1 (Python — free):                  $0
  Job 2 (Python — free):                  $0
  Job 3 (mechanical browser):            ~$0.08/run × 4/day × 30 = ~$10/month
  ─────────────────────────────────────────────────────────────────
  Total:                                  ~$10/month

POTENTIAL FUTURE SAVINGS:
  If Pinterest API access is approved OR headless browser works on a
  non-WSL machine, Job 3 becomes pure Python too → total drops to $0/month.
```
