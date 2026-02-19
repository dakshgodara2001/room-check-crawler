"""
scheduler.py — Main entry point.

Runs the crawler exactly twice a day (default 08:00 and 20:00 IST) and
dispatches notifications if any rooms are available.

Usage:
    python scheduler.py               # Uses run times from config.py
    python scheduler.py --once        # Run immediately once and exit (good for cron)
    python scheduler.py --times 07:00 19:30   # Override run times for this session
"""

import argparse
import asyncio
import logging
import logging.handlers
import sys
import time
from datetime import datetime

import schedule

import config
from crawler import run_crawler
from notifier import send_notification


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _setup_logging() -> None:
    """
    Configure root logger with:
      - Rotating file handler  → room_check.log (10 MB × 5 backups)
      - StreamHandler          → stdout
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler with rotation
    fh = logging.handlers.RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job function
# ---------------------------------------------------------------------------

def run_job() -> None:
    """
    Single crawl + notify cycle.
    This is a synchronous wrapper around the async crawler so that the
    `schedule` library (which is sync) can invoke it cleanly.
    """
    logger.info("=" * 60)
    logger.info("Job started at %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("=" * 60)

    try:
        rooms = asyncio.run(run_crawler())
        if rooms:
            logger.info("Found %d available room record(s). Sending notification.",
                        len(rooms))
            send_notification(rooms)
        else:
            logger.info("No availability found. No notification sent.")
    except Exception as exc:
        logger.exception("Unhandled exception in run_job: %s", exc)

    logger.info("Job finished at %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Scheduler loop
# ---------------------------------------------------------------------------

def start_scheduler(run_times: list[str]) -> None:
    """Register jobs and start the blocking schedule loop."""
    if not run_times:
        run_times = config.RUN_TIMES

    for t in run_times:
        schedule.every().day.at(t).do(run_job)
        logger.info("Scheduled daily run at %s", t)

    logger.info("Scheduler active. Waiting for next run time …")
    logger.info("Press Ctrl+C to stop.")

    while True:
        schedule.run_pending()
        time.sleep(30)  # Check every 30 seconds


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Haryana PWD Guest House availability crawler"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run the crawler once immediately and exit (suitable for cron).",
    )
    parser.add_argument(
        "--times",
        nargs="+",
        metavar="HH:MM",
        default=None,
        help=(
            "Override scheduled run times for this session. "
            "Example: --times 07:00 19:30"
        ),
    )
    return parser.parse_args()


def main() -> None:
    _setup_logging()
    args = _parse_args()

    logger.info("Haryana PWD Guest House Crawler starting up.")
    logger.info("Target rest houses: %s", config.TARGET_REST_HOUSES)
    logger.info("Checking %d days ahead.", config.DAYS_AHEAD)

    if args.once:
        logger.info("--once flag detected: running immediately.")
        run_job()
        sys.exit(0)

    run_times = args.times or config.RUN_TIMES
    start_scheduler(run_times)


if __name__ == "__main__":
    main()
