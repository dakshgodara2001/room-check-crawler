"""
notifier.py — Notification dispatch for room availability alerts.

Supports two backends (auto-detected from config):
  1. Telegram Bot API  — primary; set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID.
  2. Generic Webhook   — fallback; set WEBHOOK_URL in config / env.

Both backends are no-ops if their credentials are missing, so the crawler
will never crash due to a misconfigured notification setup.
"""

import json
import logging
import ssl
import textwrap
from typing import List

import certifi
import urllib.request
import urllib.error
import urllib.parse

from crawler import AvailableRoom
import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Message formatter
# ---------------------------------------------------------------------------

def format_message(rooms: List[AvailableRoom]) -> str:
    """
    Build a human-readable availability report grouped by location → date.

    Example output:
    ┌──────────────────────────────────────────┐
    │  🏨 Haryana PWD Guest House — Rooms Available  │
    │  Checked: 2025-06-18  |  Next 15 days          │
    └──────────────────────────────────────────┘

    📍 Panchkula
      ● 2025-06-19 | Haryana Niwas | AC Double | 2 rooms
      ● 2025-06-20 | Haryana Niwas | Suite      | 1 room

    📍 Gurugram
      ● 2025-06-18 | PWD Rest House | Standard  | 3 rooms
    """
    if not rooms:
        return ""

    from datetime import date
    today = date.today().isoformat()

    lines: List[str] = [
        "🏨 *Haryana PWD Guest House — Availability Alert*",
        f"_Checked: {today}  |  Next {config.DAYS_AHEAD} days_",
        "",
    ]

    # Group by location
    by_location: dict = {}
    for r in rooms:
        by_location.setdefault(r.location, []).append(r)

    for location, loc_rooms in by_location.items():
        lines.append(f"📍 *{location}*")
        # Sort by date then rest-house name
        for r in sorted(loc_rooms, key=lambda x: (x.check_date, x.rest_house)):
            room_word = "room" if r.rooms_available == 1 else "rooms"
            lines.append(
                f"  • `{r.check_date}` | {r.rest_house} "
                f"| {r.category} | *{r.rooms_available} {room_word}*"
            )
        lines.append("")

    lines.append("_Book quickly — availability changes fast!_")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Telegram backend
# ---------------------------------------------------------------------------

def _send_telegram(message: str) -> bool:
    """
    Send a Markdown-formatted message via Telegram Bot API.
    Returns True on success.
    """
    token   = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID

    if not token or token == "YOUR_BOT_TOKEN_HERE":
        logger.warning("Telegram bot token not configured; skipping Telegram.")
        return False
    if not chat_id or chat_id == "YOUR_CHAT_ID_HERE":
        logger.warning("Telegram chat ID not configured; skipping Telegram.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id":    chat_id,
        "text":       message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    try:
        with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as resp:
            body = json.loads(resp.read().decode())
            if body.get("ok"):
                logger.info("Telegram message sent successfully.")
                return True
            logger.error("Telegram API error: %s", body)
            return False
    except urllib.error.HTTPError as exc:
        logger.error("Telegram HTTP error %s: %s", exc.code, exc.read())
        return False
    except Exception as exc:
        logger.exception("Telegram send failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Generic webhook backend
# ---------------------------------------------------------------------------

def _send_webhook(rooms: List[AvailableRoom], message: str) -> bool:
    """
    POST a JSON payload to an arbitrary webhook URL.
    Returns True on success.
    """
    url = config.WEBHOOK_URL
    if not url:
        logger.debug("No WEBHOOK_URL configured; skipping webhook.")
        return False

    payload = json.dumps({
        "summary": message,
        "rooms": [
            {
                "location":        r.location,
                "rest_house":      r.rest_house,
                "date":            r.check_date,
                "category":        r.category,
                "rooms_available": r.rooms_available,
            }
            for r in rooms
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            logger.info("Webhook response: %s %s", resp.status, resp.reason)
            return resp.status < 300
    except Exception as exc:
        logger.exception("Webhook send failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_notification(rooms: List[AvailableRoom]) -> None:
    """
    Compile and dispatch availability notifications.
    Called only when `rooms` is non-empty.
    """
    if not rooms:
        logger.info("No rooms to notify about.")
        return

    message = format_message(rooms)
    logger.info("Sending notification for %d room record(s).", len(rooms))

    telegram_ok = _send_telegram(message)
    webhook_ok  = _send_webhook(rooms, message)

    if not telegram_ok and not webhook_ok:
        # Last-resort: at least print to stdout / log file
        logger.warning(
            "All notification backends failed or unconfigured. "
            "Availability summary:\n%s",
            message
        )


# ---------------------------------------------------------------------------
# Manual test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    # Synthetic test room
    test_rooms = [
        AvailableRoom(
            location="Panchkula",
            rest_house="Haryana Niwas",
            check_date="2025-06-19",
            category="AC Double Bed",
            rooms_available=2,
        ),
        AvailableRoom(
            location="Gurugram",
            rest_house="PWD Rest House",
            check_date="2025-06-20",
            category="Standard",
            rooms_available=3,
        ),
    ]
    print(format_message(test_rooms))
    send_notification(test_rooms)
