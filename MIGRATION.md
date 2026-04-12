# Migration Guide — Transferring Hermes & Jobs to Another Computer

## What Lives Where

```
~/.hermes/                          Hermes config, data, and runtime
  ├── .env                          API keys, passwords
  ├── config.yaml                   Model, settings, toolsets
  ├── auth.json                     Paired Telegram users, credentials
  ├── SOUL.md                       Agent personality
  ├── cron/
  │   ├── jobs.json                 Cron job definitions
  │   └── output/                   Run output logs
  ├── scripts/
  │   ├── trending_tech_products.py Scraper script (deployed copy)
  │   └── .venv/                    Isolated Python environment
  ├── skills/                       Installed skills
  ├── state.db                      Session history, memory
  └── sessions/                     Conversation transcripts

~/pinterest-tech-trends/            GitHub project (source of truth)
  github.com/Asif1924/pinterest-tech-trends
```

## Step 1: Create a Backup on the Old Machine

```bash
tar czf ~/hermes-backup.tar.gz \
  -C / \
  home/$USER/.hermes/.env \
  home/$USER/.hermes/config.yaml \
  home/$USER/.hermes/auth.json \
  home/$USER/.hermes/SOUL.md \
  home/$USER/.hermes/cron/ \
  home/$USER/.hermes/scripts/ \
  home/$USER/.hermes/skills/ \
  home/$USER/.hermes/state.db \
  home/$USER/.hermes/sessions/
```

If on WSL, you can access the backup from Windows at:
```
\\wsl$\Ubuntu\home\<username>\hermes-backup.tar.gz
```

## Step 2: Stop the Gateway on the Old Machine

Only one machine can run the Telegram bot at a time with the same bot token.

```bash
hermes gateway stop
```

## Step 3: Install Hermes on the New Machine

```bash
git clone https://github.com/NousResearch/hermes-agent.git ~/.hermes/hermes-agent
cd ~/.hermes/hermes-agent
./setup-hermes.sh
```

## Step 4: Restore the Backup

Copy `hermes-backup.tar.gz` to the new machine, then:

```bash
tar xzf hermes-backup.tar.gz -C /
```

This restores:
- API keys and passwords (.env)
- Model and gateway config (config.yaml)
- Telegram pairing (auth.json)
- All cron jobs and their history
- Scripts and skills
- Session history and memory

## Step 5: Deploy the Pinterest Project

```bash
git clone https://github.com/Asif1924/pinterest-tech-trends.git ~/pinterest-tech-trends
cd ~/pinterest-tech-trends
./deploy.sh
```

This creates the Python venv and syncs the script and cron job config.

## Step 6: Start Everything

```bash
# Start the Telegram bot
hermes gateway run

# Or install as a service (survives reboots)
hermes gateway install

# Start the CLI
hermes
```

## Verify

```bash
# Check gateway is running
hermes gateway status

# Check cron job is active
hermes cron list

# Test the scraper
python3 ~/.hermes/scripts/trending_tech_products.py | head -5

# Send yourself a test message
hermes cron run e5acea7d6609
```

## Notes

- The Python venv (`.venv/`) is NOT in the backup — `deploy.sh` recreates it on the new machine
- If the new machine has a different Python version, the venv will be rebuilt automatically
- Session history and memory transfer with `state.db` — the bot remembers past conversations
- The Telegram bot token, allowed users, and home channel all carry over from `.env`
- If you change machines frequently, consider installing the gateway as a service on one primary machine and using the CLI on others
