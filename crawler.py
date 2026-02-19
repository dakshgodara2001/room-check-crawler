"""
crawler.py — Async Playwright engine for Haryana PWD Guest House availability.

Architecture
------------
The Haryana PWD portal is an ASP.NET Web Forms application.  Every dropdown
change fires a __doPostBack() that triggers a full-page round-trip on the
server.  Playwright handles this transparently if we call
    page.wait_for_load_state("networkidle")
after every select_option() call.

Portal structure (confirmed from live inspection)
-------------------------------------------------
There is a SINGLE flat rest-house dropdown — no district/city pre-filter.
Selecting an entry triggers one postback that loads the dates/search form.
The crawler iterates directly over the exact option labels in TARGET_REST_HOUSES.

Confirmed element IDs (inspected live — 2026-02-19)
---------------------------------------------------
  ddltypeofperson      — User type  (G = Government Officials / P = Private Person)
  ddlhoteldestination  — Single flat rest-house list (53 options, value codes like 'PWP')
  txtcheckindate       — Check-in date  (text input, format dd/mm/yyyy)
  txtnoofdays          — Number of nights  (text input; set to "1" for a single-night check)
  txtcheckoutdate      — Check-out date  (auto-populated, but we fill it as well for safety)
  btnGo                — "Check Availability" submit button
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PWTimeout,
    async_playwright,
)

import config

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Element selectors — verified against the live portal (2026-02-19).
# Only update these if the site is redesigned.
# ---------------------------------------------------------------------------
DROPDOWN_USER_TYPE  = "#ddltypeofperson"
DROPDOWN_REST_HOUSE = "#ddlhoteldestination"   # 53-option flat list, value codes like 'PWP'
INPUT_CHECKIN       = "#txtcheckindate"         # dd/mm/yyyy text input
INPUT_NUM_DAYS      = "#txtnoofdays"            # integer nights; set to "1" per check
# NOTE: #txtcheckoutdate is disabled — the site auto-fills it from checkin + days
BUTTON_SEARCH       = "#btnGo"                  # value="Check Availability"
TABLE_RESULTS       = (
    "table.GridView, table[id*='Grid'], "
    "table[id*='gv'], table[id*='result'], "
    "table[id*='avail']"
)
POPUP_CLOSE         = (
    "button.close, .modal-header .close, "
    "[data-dismiss='modal'], #btnOk, #btnClose"
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class AvailableRoom:
    location: str
    rest_house: str
    check_date: str          # ISO format YYYY-MM-DD
    category: str
    rooms_available: int


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

async def _dismiss_popups(page: Page) -> None:
    """Quietly close any modal / overlay that may block interaction."""
    try:
        close_btn = page.locator(POPUP_CLOSE).first
        if await close_btn.is_visible(timeout=3_000):
            logger.debug("Dismissing popup.")
            await close_btn.click()
            await page.wait_for_timeout(500)
    except PWTimeout:
        pass  # No popup — that's fine.


async def _dump_selects(page: Page) -> None:
    """DEBUG helper — log all <select> IDs/names and their visible options."""
    selects = await page.query_selector_all("select")
    for sel in selects:
        sel_id   = await sel.get_attribute("id")   or "(no id)"
        sel_name = await sel.get_attribute("name") or "(no name)"
        options  = await sel.query_selector_all("option")
        texts    = [await o.inner_text() for o in options[:10]]
        logger.debug("SELECT id=%s name=%s options=%s%s",
                     sel_id, sel_name, texts,
                     " …" if len(options) > 10 else "")


async def _wait_postback(page: Page) -> None:
    """Wait for an ASP.NET postback to settle (network idle + short pause)."""
    try:
        await page.wait_for_load_state("networkidle",
                                       timeout=config.PAGE_LOAD_TIMEOUT)
    except PWTimeout:
        logger.warning("Timed out waiting for networkidle; continuing anyway.")
    await page.wait_for_timeout(500)  # Extra buffer for DOM manipulation


async def _select_by_label(page: Page, selector: str, label: str) -> bool:
    """
    Select the <option> whose visible text contains `label` (case-insensitive).
    Returns True on success, False if the element or option was not found.
    """
    # Try each comma-separated selector until one works
    for sel in [s.strip() for s in selector.split(",")]:
        try:
            elem = page.locator(sel).first
            await elem.wait_for(state="visible", timeout=5_000)
            # Get all option labels so we can do a fuzzy match
            option_labels = await elem.locator("option").all_inner_texts()
            matched = next(
                (opt for opt in option_labels
                 if label.lower() in opt.lower()),
                None
            )
            if matched is None:
                logger.warning(
                    "Label '%s' not found in %s. Available: %s",
                    label, sel, option_labels
                )
                return False
            await elem.select_option(label=matched)
            logger.debug("Selected '%s' in %s", matched, sel)
            return True
        except PWTimeout:
            continue
    logger.error("Could not locate selector '%s' on page.", selector)
    return False


async def _get_or_none(page: Page, selector: str, timeout: int = 5_000):
    """Return the first matching locator if visible, else None."""
    for sel in [s.strip() for s in selector.split(",")]:
        try:
            elem = page.locator(sel).first
            await elem.wait_for(state="visible", timeout=timeout)
            return elem
        except PWTimeout:
            continue
    return None


# ---------------------------------------------------------------------------
# Availability table parser
# ---------------------------------------------------------------------------

async def _parse_availability_table(
    page: Page,
    location: str,
    rest_house_name: str,
    check_date: date,
) -> List[AvailableRoom]:
    """
    Parse the results grid after a search is submitted.

    Confirmed table schema (id='gv'):
        Category | <checkin dd/mm/yyyy> | <checkout dd/mm/yyyy> | RoomsAvaliableStatus | Book

    The room count for our check-in date is in the column whose header equals
    the check-in date string.  There is no separate "Rest House" column — the
    rest house is already known from the dropdown selection.
    """
    results: List[AvailableRoom] = []

    table_elem = await _get_or_none(page, TABLE_RESULTS, timeout=10_000)
    if table_elem is None:
        body_text = (await page.inner_text("body")).lower()
        if any(kw in body_text for kw in
               ["no room", "not available", "no availability", "sorry"]):
            logger.info("No rooms available for %s on %s.", location, check_date)
        else:
            logger.warning(
                "Results table not found for %s on %s. "
                "The page may have changed or a CAPTCHA appeared.",
                location, check_date
            )
            if logger.isEnabledFor(logging.DEBUG):
                await page.screenshot(
                    path=f"debug_{location}_{check_date}.png"
                )
        return results

    rows = await table_elem.locator("tr").all()
    if len(rows) < 2:
        return results  # Header-only table → nothing available

    header_cells = await rows[0].locator("th, td").all_inner_texts()
    header_lower = [h.lower().strip() for h in header_cells]
    logger.debug("Table headers for %s/%s: %s", location, check_date, header_lower)

    col_category = _find_col(header_lower, ["category", "room type", "type"])
    if col_category is None:
        col_category = 0

    # Find all date columns (headers matching dd/mm/yyyy)
    date_cols = _find_date_cols(header_lower)
    if not date_cols:
        # Fallback: use check-in date at index 1
        date_cols = [(1, check_date)]

    for row in rows[1:]:
        cells = await row.locator("td").all_inner_texts()
        if not cells:
            continue
        try:
            category = cells[col_category].strip()
            if not category:
                continue
            for col_idx, col_date in date_cols:
                if col_idx >= len(cells):
                    continue
                avail_match = re.search(r"\d+", cells[col_idx].strip())
                if avail_match is None:
                    continue
                avail_count = int(avail_match.group())
                if avail_count > 0:
                    results.append(AvailableRoom(
                        location=location,
                        rest_house=rest_house_name,
                        check_date=col_date.isoformat(),
                        category=category,
                        rooms_available=avail_count,
                    ))
        except (IndexError, ValueError) as exc:
            logger.debug("Row parse error: %s | cells=%s", exc, cells)

    return results


def _find_col(headers: List[str], keywords: List[str]) -> Optional[int]:
    """Return index of first header containing any keyword, else None."""
    for i, h in enumerate(headers):
        if any(kw in h for kw in keywords):
            return i
    return None


def _find_col_exact(headers: List[str], value: str) -> Optional[int]:
    """Return index of the header that exactly equals value, else None."""
    for i, h in enumerate(headers):
        if h == value:
            return i
    return None


def _find_date_cols(headers: List[str]) -> List[tuple]:
    """Return list of (col_index, date_object) for all dd/mm/yyyy headers."""
    date_pat = re.compile(r'^(\d{2})/(\d{2})/(\d{4})$')
    result = []
    for i, h in enumerate(headers):
        m = date_pat.match(h.strip())
        if m:
            try:
                result.append((i, date(int(m.group(3)), int(m.group(2)), int(m.group(1)))))
            except ValueError:
                pass
    return result


# ---------------------------------------------------------------------------
# Core per-rest-house/per-date crawler
# ---------------------------------------------------------------------------

async def _check_rest_house_date(
    page: Page,
    rest_house_name: str,
    check_date: date,
) -> List[AvailableRoom]:
    """
    Select a rest house by its exact dropdown label, fill the date, submit,
    and return any available rooms found.

    No district step is needed — the portal exposes a single flat list of all
    rest houses.  Selecting an entry triggers one postback; the date fields and
    search button appear (or refresh) afterwards.
    """
    friendly = config.LOCATION_ALIAS.get(rest_house_name, rest_house_name)
    logger.debug("  Checking '%s' on %s …", rest_house_name, check_date)

    # --- Rest House dropdown (single flat list, triggers postback) ---
    ok = await _select_by_label(page, DROPDOWN_REST_HOUSE, rest_house_name)
    if not ok:
        logger.error("Could not select rest house '%s'. Skipping.", rest_house_name)
        return []
    await _wait_postback(page)

    # --- Date inputs ---
    # Portal uses check-in date + number of nights.
    # #txtcheckoutdate is disabled — the site populates it automatically.
    date_str = check_date.strftime("%d/%m/%Y")

    checkin_field = await _get_or_none(page, INPUT_CHECKIN)
    if checkin_field:
        await checkin_field.fill(date_str)

    num_days_field = await _get_or_none(page, INPUT_NUM_DAYS)
    if num_days_field:
        await num_days_field.fill("2")

    # --- Submit ---
    search_btn = await _get_or_none(page, BUTTON_SEARCH, timeout=5_000)
    if search_btn is None:
        logger.error("Search button not found for %s / %s.",
                     rest_house_name, check_date)
        return []
    await search_btn.click()
    await _wait_postback(page)

    # --- Parse ---
    rooms = await _parse_availability_table(page, friendly, rest_house_name, check_date)
    logger.info("  '%s' on %s → %d room(s) found.",
                rest_house_name, check_date, len(rooms))
    return rooms


# ---------------------------------------------------------------------------
# Main crawler entry point
# ---------------------------------------------------------------------------

async def run_crawler() -> List[AvailableRoom]:
    """
    Full crawl across all TARGET_REST_HOUSES × next DAYS_AHEAD dates.
    Returns aggregated list of available rooms.
    """
    all_results: List[AvailableRoom] = []
    dates_to_check = [
        date.today() + timedelta(days=d)
        for d in range(0, config.DAYS_AHEAD + 1, 3)
    ]

    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(
            headless=config.HEADLESS,
            slow_mo=config.SLOW_MO,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        context: BrowserContext = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        context.set_default_timeout(config.BROWSER_TIMEOUT)
        page: Page = await context.new_page()

        # ----------------------------------------------------------------
        # Phase 1 — Land on the portal, dismiss popups, set user type
        # ----------------------------------------------------------------
        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                logger.info("Loading portal (attempt %d/%d) …",
                            attempt, config.MAX_RETRIES)
                await page.goto(
                    config.PORTAL_URL,
                    wait_until="networkidle",
                    timeout=config.PAGE_LOAD_TIMEOUT,
                )
                await _dismiss_popups(page)

                if logger.isEnabledFor(logging.DEBUG):
                    await _dump_selects(page)

                # Select Government Officials user type
                ok = await _select_by_label(
                    page, DROPDOWN_USER_TYPE, config.USER_TYPE_LABEL
                )
                if ok:
                    await _wait_postback(page)
                else:
                    logger.warning(
                        "User type dropdown not found or label not matched. "
                        "The script will proceed without selecting it."
                    )
                break  # Success — exit retry loop

            except PWTimeout as exc:
                logger.error("Portal load timed out (attempt %d): %s",
                             attempt, exc)
                if attempt == config.MAX_RETRIES:
                    await browser.close()
                    return []
                await asyncio.sleep(config.RETRY_DELAY)

        # ----------------------------------------------------------------
        # Phase 2 — Iterate rest houses × dates
        # ----------------------------------------------------------------
        for rest_house_name in config.TARGET_REST_HOUSES:
            logger.info("=== Rest House: %s ===", rest_house_name)
            for check_date in dates_to_check:
                for attempt in range(1, config.MAX_RETRIES + 1):
                    try:
                        rooms = await _check_rest_house_date(
                            page, rest_house_name, check_date
                        )
                        all_results.extend(rooms)
                        break  # Success
                    except PWTimeout as exc:
                        logger.warning(
                            "Timeout for '%s'/%s (attempt %d): %s",
                            rest_house_name, check_date, attempt, exc
                        )
                        if attempt < config.MAX_RETRIES:
                            # Reload the page and re-select user type to recover
                            try:
                                await page.goto(
                                    config.PORTAL_URL,
                                    wait_until="networkidle",
                                    timeout=config.PAGE_LOAD_TIMEOUT,
                                )
                                await _dismiss_popups(page)
                                await _select_by_label(
                                    page, DROPDOWN_USER_TYPE,
                                    config.USER_TYPE_LABEL
                                )
                                await _wait_postback(page)
                            except Exception:
                                pass
                            await asyncio.sleep(config.RETRY_DELAY)
                        else:
                            logger.error(
                                "Giving up on '%s' / %s after %d retries.",
                                rest_house_name, check_date, config.MAX_RETRIES
                            )
                    except Exception as exc:
                        logger.exception(
                            "Unexpected error for '%s' / %s: %s",
                            rest_house_name, check_date, exc
                        )
                        break  # Non-timeout errors: skip this cell

        await browser.close()

    logger.info("Crawl complete. Total rooms found: %d", len(all_results))
    return all_results


# ---------------------------------------------------------------------------
# CLI entry point (for manual testing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import logging
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    results = asyncio.run(run_crawler())
    if results:
        for r in results:
            print(r)
    else:
        print("No availability found.")
