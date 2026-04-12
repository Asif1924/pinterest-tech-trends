# Architecture — Pinterest Tech Trends

```
Step  Description                  AI?   What does it                              Files
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

JOB 1: Trending Tech Products (every 6 hours)

1     Script scrapes 6 websites    No    Pure Python, urllib. Hits Reddit,          ~/.hermes/scripts/trending_tech_products.py
                                         Amazon, Google, TechRadar, The Verge,      ~/pinterest-tech-trends/trending_tech_products.py (source)
                                         Product Hunt. Outputs JSON to stdout.       ~/.hermes/scripts/.venv/ (isolated Python env)

2     Agent curates top 20         YES   Reads scraped JSON, picks the 20 most      ~/.hermes/cron/jobs.json (prompt that instructs the agent)
                                         pin-worthy products, writes descriptions,   ~/pinterest-tech-trends/cron_job.json (source)
                                         "why trending", price ranges, categories,
                                         and Pinterest caption ideas.

3     Agent fetches product images YES   Calls scrape_amazon_product_images()       ~/.hermes/scripts/trending_tech_products.py (function)
                                         via execute_code for each product.          (same agent turn as step 2)
                                         Gets 2 high-res Amazon images per
                                         product (1500px via CDN resizing).

4     Agent generates CSV          YES   Writes CSV via execute_code with columns:  /tmp/trending_tech_products.csv (created at runtime)
                                         Name, Category, Description, Why            (same agent turn as step 2)
                                         Trending, Price, Amazon Link, Caption,
                                         Image 1, Image 2.

5     Agent uploads CSV to Drive   YES   Uploads CSV via Google Drive API using     ~/.hermes/google_token.json (OAuth credentials)
                                         execute_code. Authenticates with OAuth,     Google Drive: PinterestAutomation/ folder
                                         refreshes token if expired.                 (same agent turn as step 2)

6     Agent emails CSV             YES   Sends email via smtplib in execute_code.   ~/.hermes/.env (EMAIL_PASSWORD, EMAIL_SMTP_HOST)
                                         SMTP to Gmail, attaches CSV, includes      (same agent turn as step 2)
                                         trend summary and Drive link in body.

7     Agent writes Telegram msg    YES   Formats plain text report: date, trend     ~/.hermes/cron/output/e5acea7d6609/*.md (run logs)
                                         summary, 20 products organized by          (same agent turn as step 2)
                                         category with affiliate links.

8     Hermes delivers to Telegram  No    Sends the agent's final response to        ~/.hermes/.env (TELEGRAM_BOT_TOKEN, TELEGRAM_HOME_CHANNEL)
                                         Telegram chat via Bot API. No AI,          ~/.hermes/config.yaml (gateway config)
                                         just an HTTP POST.

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

JOB 2: Pinterest Pin Generator (runs 30 min after Job 1) — 100% PYTHON, NO AI ($0/run)

9     Script polls Google Drive    No    Pure Python. Downloads latest CSV from      ~/.hermes/scripts/pinterest_pin_generator.py
                                         PinterestAutomation folder via Drive        ~/pinterest-tech-trends/pinterest_pin_generator.py (source)
                                         API. Checks for already-pinned products.

10    Script creates pin files     No    Pure Python. Generates a pin JSON file      ~/.hermes/pinterest_pins/pin_YYYYMMDD_NN.json
                                         for each new product with title,
                                         description, hashtags, affiliate link,
                                         images array, primary_image, alt text.

11    Script uploads pins to Drive No    Pure Python. Uploads each pin JSON to       Google Drive: PinterestAutomation/Pins/
                                         PinterestAutomation/Pins folder via
                                         Drive API. Updates existing files if
                                         they already exist.

12    Script outputs summary       No    Prints plain text report to stdout.         (relayed to Telegram by Hermes)
                                         Agent just passes it through — no
                                         AI processing needed.

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

JOB 3: Pinterest Pin Uploader (runs 1 hour after Job 2) — MECHANICAL BROWSER AUTOMATION

13    Script collects pin data     No    Pure Python. Scans pending pin files,       ~/.hermes/scripts/pinterest_pin_uploader.py
                                         reads Pinterest credentials from .env,      ~/pinterest-tech-trends/pinterest_pin_uploader.py (source)
                                         batches pins (max 5 per run), outputs
                                         JSON with all data the agent needs.

14    Agent executes browser steps min   No creativity or judgment. Follows          ~/.hermes/.env (PINTEREST_EMAIL, PINTEREST_PASSWORD)
                                         exact mechanical steps: log in to           ~/.hermes/pinterest_pins/pin_YYYYMMDD_NN.json
                                         Pinterest, navigate to pin builder,
                                         upload image, fill title/description/
                                         alt text/affiliate link, click Publish.
                                         Same steps every pin. Uses Hermes
                                         Browserbase tools (Playwright/headless
                                         doesn't work in WSL2).

15    Agent updates pin status     min   Changes pin file status from                ~/.hermes/pinterest_pins/pin_YYYYMMDD_NN.json
                                         "pending_upload" to "uploaded" or           (same agent turn as step 14)
                                         "failed" via execute_code. Adds
                                         uploaded_at timestamp.

16    Hermes delivers summary      No    Sends upload summary to Telegram.           (same delivery mechanism as step 8)

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

  FREE (no AI):                         AI / AGENT (costs tokens):
  ─────────────────────────────         ─────────────────────────────
  Step 1:  Web scraping (Python)        Step 2:  Curate top 20 products
  Step 8:  Telegram delivery            Step 3:  Fetch Amazon images
  Step 9:  Google Drive polling         Step 4:  Generate CSV
  Step 10: Create pin files (Python)    Step 5:  Upload CSV to Drive
  Step 11: Upload pins to Drive         Step 6:  Email CSV
  Step 12: Summary output (Python)      Step 7:  Write Telegram report
  Step 13: Collect pin data (Python)    Step 14: Browser clicks (mechanical, no creativity)
  Step 16: Telegram delivery            Step 15: Update pin status (mechanical)
  Deploy script
  GitHub push/pull
  Cron scheduling

  Steps 2-7:  ONE agent turn, AI judgment needed (~$0.20/run)
  Steps 9-12: ZERO cost — pure Python
  Steps 14-15: ONE agent turn, mechanical only (~$0.08/run)

MONTHLY COST ESTIMATE (4 runs/day):
  Job 1 (AI — curates products):          ~$0.20/run × 4/day × 30 = ~$24/month
  Job 2 (Python — free):                   $0
  Job 3 (mechanical browser automation):  ~$0.08/run × 4/day × 30 = ~$10/month
  ─────────────────────────────────────────────────────────────────
  Total:                                  ~$34/month

POTENTIAL FUTURE SAVINGS:
  If Pinterest API access is approved OR headless browser works on a
  non-WSL machine, Job 3 becomes pure Python too → total drops to ~$24/month.
  
  If Job 1's curation is converted to Python (rank by Reddit score, template
  descriptions), all 3 jobs become free → total drops to $0/month.
```
