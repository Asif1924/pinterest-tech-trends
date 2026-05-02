# Setup Guide — Fresh Installation on a New Hermes Instance

This guide walks you through setting up the Pinterest Tech Trends pipeline on a new computer with a fresh Hermes Agent installation.

## Prerequisites

- **Hermes Agent** installed and running (https://github.com/NousResearch/hermes-agent)
- **Python 3.8+** with `venv` support
- **Git** for cloning this repo
- **Accounts and API keys** (see Step 2 below)

---

## Step 1: Clone the Repository

```bash
git clone https://github.com/Asif1924/pinterest-tech-trends.git ~/pinterest-tech-trends
cd ~/pinterest-tech-trends
```

Verify the project structure:
```bash
ls -la
# Should show: README.md, deploy.sh, cron_job*.json, *.py, .env.example, etc.
```

---

## Step 2: Gather API Keys & Credentials

Before running `deploy.sh`, collect the following credentials. The script will copy `.env.example` and you'll fill it in with real values.

### 2a. Firecrawl API Key (Required)

Used by Job 1 to scrape trending products from web sources.

1. Visit: https://www.firecrawl.dev/
2. Sign up for a free account
3. Go to your dashboard and copy your API key
4. Save it — you'll paste it into `.env` later

### 2b. Gmail Account & App Password (Required)

Used by Job 1 to email you daily CSV reports.

1. Use your Gmail account (or create a dedicated one for automation)
2. Enable 2-Step Verification (if not already enabled):
   - Go to https://myaccount.google.com/security
   - Click "2-Step Verification"
3. Generate an App Password:
   - Go to https://myaccount.google.com/apppasswords
   - Select "Mail" and "Windows Computer"
   - Copy the 16-character password (e.g., `xxxx xxxx xxxx xxxx`)
   - **DO NOT use your regular Gmail password** — the app password is more secure

### 2c. Telegram Bot & User ID (Required)

Used by all 3 jobs to send you notifications and status updates.

1. Open Telegram and search for **@BotFather**
2. Send `/start` and follow the prompts to create a new bot
3. BotFather will give you a **Bot Token** (e.g., `123456789:ABCdefGHIjklmnoPQRstuvWXYZ_1a2b3c4d`)
4. Save the token
5. To get your Telegram user ID:
   - Search for **@userinfobot** on Telegram
   - Send it any message
   - It will reply with your numeric ID (e.g., `1234567890`)

### 2d. Pinterest Account & Credentials (Required)

Used by Job 3 to upload pins to your Pinterest board.

1. Have your Pinterest login email and password ready
2. Ensure you have a board named exactly **SmartyPants2786** (or update `config.json` with your actual board name)
3. **Note:** Storing passwords in `.env` is risky. Consider:
   - Using a dedicated Pinterest account for automation (not your main account)
   - Using a strong, unique password
   - Protecting the `.env` file with `chmod 600`

### 2e. Google Drive Folder IDs (Optional)

If you want to store CSVs and pin files on Google Drive instead of locally:

1. Create two folders in Google Drive:
   - One for CSV reports (e.g., "PinterestAutomation")
   - One for pin JSON files (e.g., "PinterestAutomation/Pins")
2. Open each folder and copy the folder ID from the URL:
   - URL format: `https://drive.google.com/drive/folders/FOLDER_ID`
   - Example: `https://drive.google.com/drive/folders/1w-XAxZccQ4wk4NOKwm2YDusouLvO-a6L`
   - Copy just the ID part: `1w-XAxZccQ4wk4NOKwm2YDusouLvO-a6L`

### 2f. LM Studio or OpenRouter (Optional)

If you want AI-powered product descriptions or enhanced features:

- **LM Studio** (local, free):
  - Download from https://lmstudio.ai/
  - Install and load a model (e.g., `qwen2.5-coder-14b-instruct`)
  - Note the server address (usually `http://localhost:1234/v1`)

- **OpenRouter** (cloud, paid):
  - Get API key from https://openrouter.ai/keys

---

## Step 3: Create the `.env` File

1. Copy the template:
   ```bash
   cp .env.example ~/.hermes/.env
   ```
   
   **Important:** Copy to `~/.hermes/.env`, NOT to the repo directory. This keeps secrets out of git.

2. Edit the file with your credentials:
   ```bash
   nano ~/.hermes/.env
   ```

3. Fill in **at minimum** these required fields:
   ```
   FIRECRAWL_API_KEY=fc-your-key-here
   EMAIL_ADDRESS=your-email@gmail.com
   EMAIL_PASSWORD=xxxx xxxx xxxx xxxx
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklmnoPQRstuvWXYZ
   TELEGRAM_HOME_CHANNEL=1234567890
   PINTEREST_EMAIL=your-pinterest-email@gmail.com
   PINTEREST_PASSWORD=your-pinterest-password
   PINTEREST_BOARD_NAME=SmartyPants2786
   ```

4. Optional: Fill in Google Drive folder IDs, LM Studio info, etc.

5. Save and verify permissions:
   ```bash
   chmod 600 ~/.hermes/.env
   cat ~/.hermes/.env  # Verify it was created
   ```

---

## Step 4: Copy `config.json`

The pipeline also needs a `config.json` file with board names, timeouts, and scoring weights.

```bash
cp config.json ~/.hermes/scripts/pinterest_config.json
```

You can edit it later if you want to adjust timeouts or scoring, but the defaults should work.

---

## Step 5: Run the Deploy Script

The deploy script will:
- Copy all three Python scripts to `~/.hermes/scripts/`
- Create a Python virtual environment with required dependencies
- Install Playwright Chromium for browser automation
- Update or create the three cron jobs in Hermes

```bash
cd ~/pinterest-tech-trends
./deploy.sh
```

Expected output:
```
Pinterest Tech Trends - Deploy
===============================
...
1. Deploying scraper script...
   ✓ Copied to ~/.hermes/scripts/trending_tech_products.py
   ✓ Copied to ~/.hermes/scripts/pinterest_pin_generator.py
   ✓ Copied to ~/.hermes/scripts/pinterest_pin_uploader.py
   ...
2. Managing Python virtual environment...
   ✓ Created venv using system Python
   ✓ Packages installed
   ✓ Playwright Chromium ready
   ...
3. Updating cron jobs...
   (No existing jobs found. You may need to create them manually.)
   ...
4. Verification...
   ✓ Script installed at ~/.hermes/scripts/trending_tech_products.py
   ✓ Venv ready at ~/.hermes/scripts/.venv
   ✓ Script runs successfully in venv
```

### If deployment fails:
- Check that Hermes is installed: `hermes --version`
- Ensure `~/.hermes/` directory exists
- Verify Python 3 is available: `python3 --version`
- Check venv support: `python3 -m venv --help`

---

## Step 6: Create the Cron Jobs

If the deploy script didn't find existing jobs, you'll need to create them manually. Hermes will create new job IDs automatically.

### Job 1: Trending Tech Products (every hour)

```bash
hermes cron create \
  --name "Trending Tech Products for Pinterest" \
  --schedule "0 * * * *" \
  --script "trending_tech_products.py"
```

### Job 2: Pinterest Pin Generator (every 6 hours, offset by 30 min)

```bash
hermes cron create \
  --name "Pinterest Pin Generator" \
  --schedule "30 */6 * * *" \
  --script "pinterest_pin_generator.py"
```

### Job 3: Pinterest Pin Uploader (4x daily: 1am, 7am, 1pm, 7pm)

```bash
hermes cron create \
  --name "Pinterest Pin Uploader" \
  --schedule "0 1,7,13,19 * * *" \
  --script "pinterest_pin_uploader.py"
```

### Verify all jobs were created:

```bash
hermes cron list
```

You should see all three jobs with their schedules and next run times.

---

## Step 7: Test the Pipeline

### Test Job 1 (manually scrape and report)

```bash
JOB_ID=$(hermes cron list | grep "Trending Tech Products" | awk '{print $1}')
hermes cron run $JOB_ID
```

Expected behavior:
- Scrapes trending tech products from Reddit, Amazon, Google, etc.
- Fetches product images
- Sends a report to your Telegram
- (Optionally) emails you a CSV

Check your Telegram for the report. It should show:
```
📊 Trending Tech Products Report
Top 20 products found:
1. Product Name (Score: 5.2) - $XXX
2. Product Name (Score: 4.8) - $XXX
...
```

### Test Job 2 (manually generate pins)

```bash
JOB_ID=$(hermes cron list | grep "Pinterest Pin Generator" | awk '{print $1}')
hermes cron run $JOB_ID
```

Expected behavior:
- Polls for the latest CSV report
- Creates pin JSON files with descriptions, hashtags, images
- Uploads to Google Drive or local storage
- Sends a summary to Telegram

### Test Job 3 (manually prepare upload batch)

```bash
JOB_ID=$(hermes cron list | grep "Pinterest Pin Uploader" | awk '{print $1}')
hermes cron run $JOB_ID
```

Expected behavior:
- Reads pending pin files
- Generates a Pinterest-compatible CSV
- Sends the CSV to your email with manual upload instructions
- Sends a summary to Telegram

---

## Step 8: Verify Telegram Integration

After running Job 1, check your Telegram:

1. Open Telegram and search for your bot (it's in the name you gave BotFather)
2. Start a conversation with it
3. You should receive messages from the cron jobs

If you don't see messages:
- Verify `TELEGRAM_BOT_TOKEN` is correct in `~/.hermes/.env`
- Verify `TELEGRAM_HOME_CHANNEL` is your actual numeric user ID (not a username)
- Check Hermes logs: `hermes logs` or `~/.hermes/cron/output/`

---

## Step 9: Enable Automatic Scheduling

Once testing is complete, the cron jobs will run automatically on their schedules:

- **Job 1** runs every hour, starting at the top of each hour
- **Job 2** runs every 6 hours at :30 (1:30am, 7:30am, 1:30pm, 7:30pm)
- **Job 3** runs 4 times daily at 1am, 7am, 1pm, and 7pm

To disable a job temporarily:
```bash
hermes cron pause <job_id>
```

To re-enable:
```bash
hermes cron resume <job_id>
```

---

## Troubleshooting

### "ERROR: Hermes home not found"
- Hermes Agent is not installed
- Install from: https://github.com/NousResearch/hermes-agent

### ".env file not found" or "FIRECRAWL_API_KEY not set"
- You skipped Step 3 or didn't save `.env` correctly
- Check: `cat ~/.hermes/.env`
- Verify it's in the right location (not in the repo directory)

### "Script not found in venv"
- The venv wasn't created properly
- Try: `rm -rf ~/.hermes/scripts/.venv && ./deploy.sh`

### Telegram messages not arriving
- Wrong `TELEGRAM_HOME_CHANNEL` (should be numeric ID, not username)
- Wrong `TELEGRAM_BOT_TOKEN`
- Hermes gateway not running: `hermes gateway status`
- Check Hermes logs: `~/.hermes/cron/output/`

### Playwright Chromium installation failed
- The uploader will fall back to system Chrome
- If you need Playwright, try: `~/.hermes/scripts/.venv/bin/python3 -m playwright install chromium`

### Pinterest login fails
- Password or email incorrect
- Pinterest account is locked or requires 2FA
- Try logging in manually first to verify credentials

---

## Next Steps

Once the pipeline is running:

1. **Customize product filtering:**
   - Edit `procured_products.json` to track which products you've already purchased
   - Add to `config.json` to adjust scoring weights or add/remove scraping sources

2. **Monitor performance:**
   - Check `~/.hermes/cron/output/` for job logs
   - Review Telegram reports for trends

3. **Scale up:**
   - Add more Pinterest boards by duplicating the jobs with different board names
   - Adjust schedules based on how frequently you want new pins

4. **Backup your setup:**
   - Save `~/.hermes/.env` and `~/.hermes/cron/jobs.json` somewhere safe
   - See `MIGRATION.md` for backing up and transferring to another machine

---

## Support

For issues or questions:
- Check `README.md` for architecture details
- Review `ARCHITECTURE.md` for step-by-step job breakdown
- Check `MIGRATION.md` for transfer to another computer

---

**Happy pinning!** 📌
