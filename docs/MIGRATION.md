# Migration Guide — Transferring Hermes & Jobs to Another Computer

## What Lives Where

```
~/.hermes/                              Hermes config, data, and runtime
  ├── .env                              API keys, passwords (Zernio, SMTP, Telegram, …)
  ├── config.yaml                       Model, settings, toolsets
  ├── auth.json                         Paired Telegram users
  ├── SOUL.md                           Agent personality
  ├── cron/
  │   ├── jobs.json                     Cron job definitions
  │   └── output/                       Per-execution run logs
  ├── scripts/
  │   ├── trending_tech_products.py     Job 1 (deployed copy)
  │   ├── pinterest_pin_generator.py    Job 2
  │   ├── pinterest_pin_uploader.py     Job 3
  │   ├── pinterest_pipeline_health.py  Retention + alerter
  │   ├── pipeline_paths.py
  │   ├── pipeline_manifest.py
  │   ├── pinterest_config.json
  │   ├── procured_products.json
  │   └── .venv/                        Isolated Python environment
  ├── pinterest/                        Pipeline data (run dirs + archives)
  │   ├── runs/<RUN_ID>/…
  │   ├── current → runs/<RUN_ID>
  │   └── archive/<RUN_ID>.tar.gz
  ├── skills/                           Installed skills
  ├── state.db                          Session history, memory
  └── sessions/                         Conversation transcripts

~/pinterest-tech-trends/                GitHub project (source of truth)
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
  home/$USER/.hermes/pinterest/ \
  home/$USER/.hermes/skills/ \
  home/$USER/.hermes/state.db \
  home/$USER/.hermes/sessions/
```

The Python venv (`scripts/.venv/`) can be excluded — `deploy.sh` recreates it
on the new machine. To exclude it explicitly:

```bash
tar czf ~/hermes-backup.tar.gz \
  --exclude='home/$USER/.hermes/scripts/.venv' \
  -C / \
  home/$USER/.hermes/
```

On WSL, the archive is reachable from Windows at
`\\wsl$\Ubuntu\home\<username>\hermes-backup.tar.gz`.

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

```bash
tar xzf hermes-backup.tar.gz -C /
```

This restores `.env`, `config.yaml`, `auth.json`, cron definitions, scripts,
skills, session DB, and — critically — the entire `~/.hermes/pinterest/` tree
including the `current` symlink and all historical runs.

## Step 5: Deploy the Pinterest Project

```bash
git clone https://github.com/Asif1924/pinterest-tech-trends.git ~/pinterest-tech-trends
cd ~/pinterest-tech-trends
./deploy.sh
```

`deploy.sh` rebuilds the venv, installs Python dependencies, and refreshes
the cron job definitions from `cron_job*.json`.

## Step 6: Start Everything

```bash
hermes gateway run          # foreground
# or
hermes gateway install      # install as a service
hermes                      # CLI
```

## Verify

```bash
hermes gateway status
hermes cron list

# Spot-check the scripts inside the deployed venv
~/.hermes/scripts/.venv/bin/python -c "import pipeline_paths, pipeline_manifest; print('OK')"

# Trigger Job 1 end-to-end (Job 2 + 3 chain automatically)
hermes cron run "$(hermes cron list | awk '/Trending Tech Products/ {print $1; exit}')"

# Inspect the latest run
ls -la ~/.hermes/pinterest/current/
cat ~/.hermes/pinterest/current/manifest.json
```

## Notes

- The venv is intentionally excluded from the backup; `deploy.sh` rebuilds it.
- `state.db` carries session history and memory.
- The `current` symlink is a *relative* link (`runs/<RUN_ID>`); it survives a
  `tar` round-trip cleanly.
- If you change machines frequently, keep the gateway installed as a service
  on one primary machine and use the CLI on the others — only one machine
  should hold the active Telegram bot token at a time.
