"""
config.py — Central configuration for the Haryana PWD Guest House Crawler.

HOW TO CONFIGURE:
  1. Fill in your Telegram bot token and chat ID (see README.md for how to get them).
  2. TARGET_REST_HOUSES contains the exact option labels from the portal dropdown.
     Update them only if the site renames an entry.
  3. Leave HEADLESS = True for server/cron deployments; set False to watch the browser.
"""

import os
from typing import Dict, List

# ---------------------------------------------------------------------------
# Telegram credentials  (set via environment variables OR hard-code here)
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID: str   = os.getenv("TELEGRAM_CHAT_ID",   "YOUR_CHAT_ID_HERE")

# Alternatively, if you prefer a generic outbound webhook instead of Telegram,
# set WEBHOOK_URL and the notifier will POST JSON to it.
WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")

# ---------------------------------------------------------------------------
# Portal settings
# ---------------------------------------------------------------------------
PORTAL_URL: str = "https://www.hryguesthouse.gov.in/frmmainlogin.aspx"

# The label exactly as it appears in the "User Type" dropdown on the portal.
USER_TYPE_LABEL: str = "Government Officials"   # exact label in ddltypeofperson

# ---------------------------------------------------------------------------
# Search parameters
# ---------------------------------------------------------------------------
DAYS_AHEAD: int = 15          # Check today through today + DAYS_AHEAD (inclusive)

# Exact rest-house labels as they appear in the portal's single dropdown.
# N Delhi has two separate entries — both are listed so both get checked.
TARGET_REST_HOUSES: List[str] = [
    "PWD BR Rest House Panchkula",
    "Hry SGH Chanakyapuri N Delhi",
    "Hry Bhawan Cop Marg N Delhi",
    "PWD BR Rest House Gurugram",
    "Ekant RH Mussorrie",
    "Benmore Circuit House Shimla",
]

# Human-friendly city label for each rest house — used only in notifications.
LOCATION_ALIAS: Dict[str, str] = {
    "PWD BR Rest House Panchkula":    "Panchkula",
    "Hry SGH Chanakyapuri N Delhi":   "N Delhi",
    "Hry Bhawan Cop Marg N Delhi":    "N Delhi",
    "PWD BR Rest House Gurugram":     "Gurugram",
    "Ekant RH Mussorrie":             "Mussorrie",
    "Benmore Circuit House Shimla":   "Shimla",
    "PWD RH Uchana":                  "Uchana",
}

# ---------------------------------------------------------------------------
# Browser / Playwright settings
# ---------------------------------------------------------------------------
HEADLESS: bool = True          # Set to False to debug visually
BROWSER_TIMEOUT: int = 30_000  # ms — default timeout for Playwright actions
PAGE_LOAD_TIMEOUT: int = 60_000  # ms — full-page / network-idle timeout
SLOW_MO: int = 0               # ms delay between Playwright actions (0 = fastest)

# ---------------------------------------------------------------------------
# Retry / resilience
# ---------------------------------------------------------------------------
MAX_RETRIES: int = 3           # Retry each location/date block this many times
RETRY_DELAY: int = 10          # seconds to wait between retries

# ---------------------------------------------------------------------------
# Scheduling  (24-hour times for the twice-daily runs)
# ---------------------------------------------------------------------------
RUN_TIMES: List[str] = ["08:00", "20:00"]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FILE: str = "room_check.log"
LOG_LEVEL: str = "INFO"        # DEBUG | INFO | WARNING | ERROR
