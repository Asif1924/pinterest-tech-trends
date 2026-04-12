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

JOB 2: Pinterest Pin Generator (runs 30 min after Job 1)

9     Script polls Google Drive    No    Pure Python. Downloads latest CSV from      ~/.hermes/scripts/pinterest_pin_generator.py
                                         PinterestAutomation folder via Drive        ~/pinterest-tech-trends/pinterest_pin_generator.py (source)
                                         API, checks for already-pinned products,
                                         outputs JSON with product data + images.

10    Agent creates pin files      YES   Reads product data, generates a pin         ~/.hermes/cron/jobs.json (prompt)
                                         JSON file for each new product with          ~/pinterest-tech-trends/cron_job_pins.json (source)
                                         title, description, hashtags, affiliate
                                         link, images array, primary_image,
                                         and alt text.

11    Agent uploads pins to Drive  YES   Uploads each pin JSON to Google Drive       ~/.hermes/pinterest_pins/pin_YYYYMMDD_NN.json (local)
                                         PinterestAutomation/Pins folder via         Google Drive: PinterestAutomation/Pins/ (remote)
                                         execute_code. Same OAuth flow as Job 1.     (same agent turn as step 10)

12    Hermes delivers summary      No    Sends pin creation summary to Telegram.     (same delivery mechanism as step 8)

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

JOB 3: Pinterest Pin Uploader (runs 1 hour after Job 2) — PAUSED until Pinterest API approved

13    Script scans pending pins    No    Pure Python. Scans ~/.hermes/pinterest_pins/  ~/.hermes/scripts/pinterest_pin_uploader.py
                                         for pin files with status "pending_upload".    ~/pinterest-tech-trends/pinterest_pin_uploader.py (source)
                                         Checks Pinterest API credentials.
                                         Outputs JSON with pending pins.

14    Agent uploads to Pinterest   YES   For each pending pin, calls Pinterest          ~/.hermes/.env (PINTEREST_ACCESS_TOKEN)
                                         v5 API to create a pin on the                  ~/.hermes/pinterest_pins/pin_YYYYMMDD_NN.json
                                         SmartyPants9786 board. Uses primary_image,     (same agent turn)
                                         title, description, affiliate link.
                                         Rate limited: 2s between uploads.

15    Agent updates pin status     YES   Changes each pin file status from              ~/.hermes/pinterest_pins/pin_YYYYMMDD_NN.json
                                         "pending_upload" to "uploaded" (or "failed").   (same agent turn as step 14)
                                         Adds pinterest_pin_id and uploaded_at.

16    Hermes delivers summary      No    Sends upload summary to Telegram.              (same delivery mechanism as step 8)

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

SUPPORTING FILES

      Deploy script                No    Copies scripts, creates venv, updates       ~/pinterest-tech-trends/deploy.sh
                                         cron jobs from repo to Hermes.

      GitHub repo                  No    Source of truth for all editable files.     ~/pinterest-tech-trends/
                                                                                     github.com/Asif1924/pinterest-tech-trends

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

SUMMARY: What uses AI tokens vs what's free

  FREE (no AI):                         AI (costs tokens):
  ─────────────────────────────         ─────────────────────────────
  Step 1:  Web scraping (Python)        Step 2:  Curate top 20 products
  Step 8:  Telegram delivery            Step 3:  Fetch Amazon images
  Step 9:  Google Drive polling         Step 4:  Generate CSV
  Step 12: Telegram delivery            Step 5:  Upload CSV to Drive
  Step 13: Scan pending pins            Step 6:  Email CSV
  Step 16: Telegram delivery            Step 7:  Write Telegram report
  Deploy script                         Step 10: Create pin JSON files
  GitHub push/pull                      Step 11: Upload pins to Drive
  Cron scheduling                       Step 14: Upload pins to Pinterest
                                        Step 15: Update pin file status

  Steps 2-7 are ONE agent turn (~$0.15-0.25 on Sonnet)
  Steps 10-11 are ONE agent turn (~$0.10-0.15 on Sonnet)
  Steps 14-15 are ONE agent turn (~$0.10-0.15 on Sonnet)
```
