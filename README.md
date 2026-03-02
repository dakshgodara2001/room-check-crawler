# Room Check

A PM got tired of manually refreshing [hryguesthouse.gov.in](https://www.hryguesthouse.gov.in/frmmainlogin.aspx) every day, so now a robot does it instead.

Checks availability across Haryana PWD guest houses (Panchkula, Delhi, Gurugram, Mussoorie, Shimla) for the next 15 days and pings you on Telegram when something opens up.

## How it works

1. Playwright opens the portal in a headless browser
2. Picks each guest house from the dropdown, fills in dates, hits search
3. Parses the results table for available rooms
4. Sends you a Telegram message if anything is found

Runs twice a day (8 AM and 8 PM) by default. Or just run it once whenever you're feeling lucky.

## Quick start

```bash
pip install -r requirements.txt
playwright install chromium

# one-shot run
python scheduler.py --once

# or let it run on schedule
python scheduler.py
```

## Telegram notifications

Drop your bot token and chat ID into `config.py` (or set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as env vars). That's it.

## What to tweak in `config.py`

- **`TARGET_REST_HOUSES`** — which guest houses to check
- **`DAYS_AHEAD`** — how far ahead to look (default 15)
- **`RUN_TIMES`** — when to run (default 8 AM + 8 PM)
- **`HEADLESS`** — set `False` to watch the browser do its thing

## Project layout

```
config.py        ← all settings
crawler.py       ← the Playwright scraping engine
notifier.py      ← Telegram / webhook alerts
scheduler.py     ← entry point
```
