# Haryana PWD Guest House — Room Availability Crawler

Automated checker for [hryguesthouse.gov.in](https://www.hryguesthouse.gov.in/frmmainlogin.aspx).
Runs twice a day, scrapes availability for the next 15 days across five target locations,
and sends a Telegram (or webhook) alert only when rooms are found.

---

## Project Layout

```
room-check/
├── config.py        ← All settings live here (tokens, locations, schedule)
├── crawler.py       ← Async Playwright scraping engine
├── notifier.py      ← Telegram / webhook notification dispatch
├── scheduler.py     ← Entry point; runs the job on a schedule
└── requirements.txt
```

---

## 1 — Prerequisites

| Requirement | Minimum version |
|-------------|-----------------|
| Python      | 3.10+           |
| pip         | 23+             |
| Chrome / Chromium (headless) | installed by Playwright (see below) |

---

## 2 — Installation

```bash
# 1. Clone / copy the project folder
cd room-check

# 2. Create and activate a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install Playwright's bundled Chromium browser
playwright install chromium
playwright install-deps chromium   # Linux servers: installs OS-level deps
```

---

## 3 — Telegram Bot Setup

> Skip this section if you prefer the webhook backend.

### 3a — Create your bot

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts.
3. Copy the **API token** (looks like `123456789:ABCdef…`).

### 3b — Find your Chat ID

1. Search for **@userinfobot** on Telegram and send it any message.
2. It replies with your numeric **chat ID** (e.g. `987654321`).
   For a group, add the bot to the group and use the group's negative ID.

### 3c — Configure

**Option A — environment variables (recommended for servers):**

```bash
export TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ"
export TELEGRAM_CHAT_ID="987654321"
```

Add those lines to `~/.bashrc` / `~/.zshrc` (or a `.env` file you source before running).

**Option B — edit `config.py` directly:**

```python
TELEGRAM_BOT_TOKEN = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ"
TELEGRAM_CHAT_ID   = "987654321"
```

### 3d — Test the notification

```bash
python notifier.py   # Sends a synthetic test message
```

---

## 4 — Webhook Setup (alternative to Telegram)

Set the `WEBHOOK_URL` environment variable (or `config.py`) to any URL that
accepts a POST with `Content-Type: application/json`.  The payload shape is:

```json
{
  "summary": "Human-readable Markdown message",
  "rooms": [
    {
      "location": "Panchkula",
      "rest_house": "Haryana Niwas",
      "date": "2025-06-19",
      "category": "AC Double Bed",
      "rooms_available": 2
    }
  ]
}
```

Compatible with **Slack incoming webhooks**, **Make (Integromat)**, **n8n**, etc.

---

## 5 — Running the Crawler

### One-shot run (test immediately)

```bash
python scheduler.py --once
```

### Continuous scheduled process (08:00 + 20:00 by default)

```bash
python scheduler.py
```

Override the run times for the current session:

```bash
python scheduler.py --times 07:00 19:30
```

Change the **permanent** schedule by editing `config.py`:

```python
RUN_TIMES = ["06:00", "18:00"]
```

---

## 6 — Deploying as a Cron Job (Linux / macOS)

This is the most reliable approach for unattended servers.

```bash
crontab -e
```

Add (adjust paths to your actual venv and project folder):

```cron
# Haryana PWD room checker — runs at 08:00 and 20:00 IST (UTC+5:30 → UTC 02:30 / 14:30)
30 2  * * * /home/ubuntu/room-check/.venv/bin/python /home/ubuntu/room-check/scheduler.py --once >> /home/ubuntu/room-check/cron.log 2>&1
30 14 * * * /home/ubuntu/room-check/.venv/bin/python /home/ubuntu/room-check/scheduler.py --once >> /home/ubuntu/room-check/cron.log 2>&1
```

> **Tip for IST servers:** If your server is already in the `Asia/Kolkata`
> timezone, use `0 8` and `0 20` instead.

---

## 7 — Deploying as a systemd Service (Linux)

Create `/etc/systemd/system/room-check.service`:

```ini
[Unit]
Description=Haryana PWD Guest House Room Checker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/room-check
Environment="TELEGRAM_BOT_TOKEN=YOUR_TOKEN_HERE"
Environment="TELEGRAM_CHAT_ID=YOUR_CHAT_ID_HERE"
ExecStart=/home/ubuntu/room-check/.venv/bin/python scheduler.py
Restart=on-failure
RestartSec=60

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable room-check
sudo systemctl start room-check
sudo journalctl -u room-check -f    # tail logs
```

---

## 8 — Adjusting Site Selectors

The portal is an **ASP.NET Web Forms** app.  If a selector fails:

1. Open the site in **Chrome DevTools → Elements** tab.
2. Find the `<select>` for district, rest house, etc.
3. Note its `id` attribute (often `ContentPlaceHolder1_ddlDistrict`).
4. Update the matching constant in `crawler.py` (top of the file, all-caps).

Run with debug logging to see a live dump of all dropdowns:

```bash
LOG_LEVEL=DEBUG python scheduler.py --once
```

Screenshots are automatically saved as `debug_<location>_<date>.png`
when a results table cannot be found (useful for diagnosing CAPTCHA pages
or unexpected redirects).

---

## 9 — Configuration Reference

| Setting | File | Default | Purpose |
|---------|------|---------|---------|
| `TELEGRAM_BOT_TOKEN` | `config.py` / env | — | Telegram bot credential |
| `TELEGRAM_CHAT_ID`   | `config.py` / env | — | Destination chat/group |
| `WEBHOOK_URL`        | `config.py` / env | `""` | Generic POST webhook |
| `TARGET_REST_HOUSES` | `config.py` | 6 rest houses | Exact dropdown labels to check |
| `DAYS_AHEAD`         | `config.py` | `15` | How many days forward |
| `RUN_TIMES`          | `config.py` | `["08:00","20:00"]` | Daily schedule |
| `HEADLESS`           | `config.py` | `True` | Show browser window |
| `MAX_RETRIES`        | `config.py` | `3` | Retries per location/date |
| `LOG_LEVEL`          | `config.py` | `INFO` | `DEBUG`/`INFO`/`WARNING` |
| `LOG_FILE`           | `config.py` | `room_check.log` | Log file path |

---

## 10 — Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `TimeoutError` on page load | Slow government server | Increase `PAGE_LOAD_TIMEOUT` in `config.py` |
| Dropdown not found | Selector ID changed | Inspect DevTools, update selector in `crawler.py` |
| "Label not matched" warning | Rest house name differs on site | Run `LOG_LEVEL=DEBUG` to see available options and update `TARGET_REST_HOUSES` |
| Telegram message not received | Wrong token / chat ID | Verify with `python notifier.py` |
| Blank results every time | CAPTCHA present | The site may have added a CAPTCHA; check `debug_*.png` screenshots |
| `playwright install` fails | Missing OS deps | Run `playwright install-deps chromium` with `sudo` |

---

## 11 — Legal & Ethical Note

This script is for **personal notification purposes only** — checking publicly
available government accommodation for your own use.  Do not flood the server
with high-frequency requests; the default 15-day × 5-location scan with a
twice-daily schedule is designed to be low-impact.
