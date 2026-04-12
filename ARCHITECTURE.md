# Architecture — Pinterest Tech Trends

```
Step  Description                  AI?   What does it                              Files
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

1     Script scrapes 6 websites    No    Pure Python, urllib. Hits Reddit,          ~/.hermes/scripts/trending_tech_products.py
                                         Amazon, Google, TechRadar, The Verge,      ~/pinterest-tech-trends/trending_tech_products.py (source)
                                         Product Hunt. Outputs JSON to stdout.       ~/.hermes/scripts/.venv/ (isolated Python env)

2     Agent curates top 20         YES   Reads scraped JSON, picks the 20 most      ~/.hermes/cron/jobs.json (prompt that instructs the agent)
                                         pin-worthy products, writes descriptions,   ~/pinterest-tech-trends/cron_job.json (source)
                                         "why trending", price ranges, categories,
                                         and Pinterest caption ideas.

3     Agent generates CSV          YES   Writes CSV via execute_code with columns:  /tmp/trending_tech_products.csv (created at runtime, temporary)
                                         Name, Category, Description, Why           (same agent turn as step 2)
                                         Trending, Price, Amazon Link, Caption.

4     Agent emails CSV             YES   Sends email via smtplib in execute_code.   ~/.hermes/.env (EMAIL_PASSWORD, EMAIL_SMTP_HOST)
                                         SMTP to Gmail, attaches CSV, includes      (same agent turn as step 2)
                                         trend summary in body.

5     Agent writes Telegram msg    YES   Formats plain text report: date, trend     ~/.hermes/cron/output/e5acea7d6609/*.md (run logs)
                                         summary, 20 products organized by          (same agent turn as step 2)
                                         category with affiliate links.

6     Hermes delivers to Telegram  No    Sends the agent's final response to        ~/.hermes/.env (TELEGRAM_BOT_TOKEN, TELEGRAM_HOME_CHANNEL)
                                         Telegram chat via Bot API. No AI,          ~/.hermes/config.yaml (gateway config)
                                         just an HTTP POST.

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Supporting files:

      Deploy script                No    Copies script, creates venv, updates       ~/pinterest-tech-trends/deploy.sh
                                         cron job from repo to Hermes.

      GitHub repo                  No    Source of truth for all editable files.     ~/pinterest-tech-trends/
                                                                                     github.com/Asif1924/pinterest-tech-trends

──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

JOB 2: Pinterest Pin Generator (runs 30 min after Job 1)

7     Script polls Google Drive    No    Pure Python. Downloads latest CSV from      ~/.hermes/scripts/pinterest_pin_generator.py
                                         PinterestAutomation folder, checks for      ~/pinterest-tech-trends/pinterest_pin_generator.py (source)
                                         already-pinned products, outputs JSON.

8     Agent creates pin files      YES   Reads product data, generates a pin         ~/.hermes/cron/jobs.json (prompt)
                                         JSON file for each new product with          ~/pinterest-tech-trends/cron_job_pins.json (source)
                                         title, description, hashtags, affiliate
                                         link, image search query, and alt text.

9     Pin files saved to disk      YES   Writes individual JSON files, one per       ~/.hermes/pinterest_pins/pin_YYYYMMDD_NN.json
                                         product. Status: "pending_upload" for        (same agent turn as step 8)
                                         a future upload job to consume.

10    Hermes delivers summary      No    Sends pin creation summary to Telegram.     (same delivery as Job 1)
```
