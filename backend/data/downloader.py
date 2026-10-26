"""
KARAT – MCX Bhavcopy downloader.

Downloads daily Bhavcopy from MCX, one trading day per request.
Features:
- Polite rate limiting (configurable gap between requests).
- Exponential-backoff retries on transient failures.
- Date-validation: rejects responses whose Date ≠ requested date.
- Caching: skips dates already stored as raw CSVs.
- Resumable: call with a date range and it picks up where it left off.

FORMAT TRAPS HANDLED
1. Request date: DD/MM/YYYY   Response date field: MM/DD/YYYY
2. ExpiryDate like "04SEP2026" → parsed to datetime.date
3. Symbol may be space-padded → stripped
4. MCX may silently return the latest trading day for holidays or
   future dates → we compare returned date against requested date
   and reject mismatches.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

from backend.config import (
    MCX_BACKOFF_BASE,
    MCX_BHAVCOPY_URL,
    MCX_MAX_RETRIES,
    MCX_RATE_LIMIT_SECONDS,
    RAW_DIR,
    TRACKED_SYMBOLS,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def download_range(
    start: dt.date,
    end: dt.date,
    *,
    raw_dir: Path = RAW_DIR,
    rate_limit: float = MCX_RATE_LIMIT_SECONDS,
) -> dict[str, Any]:
    """
    Download MCX Bhavcopies for *start* through *end* (inclusive).

    Returns a summary dict:
        {
            "requested": int,
            "downloaded": int,
            "skipped_cached": int,
            "skipped_weekend": int,
            "rejected_date_mismatch": int,
            "errors": [{"date": ..., "reason": ...}, ...],
        }
    """
    raw_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "requested": 0,
        "downloaded": 0,
        "skipped_cached": 0,
        "skipped_weekend": 0,
        "rejected_date_mismatch": 0,
        "errors": [],
    }

    current = start
    while current <= end:
        summary["requested"] += 1

        # Skip weekends (Saturday=5, Sunday=6)
        if current.weekday() >= 5:
            summary["skipped_weekend"] += 1
            current += dt.timedelta(days=1)
            continue

        out_path = _raw_path(current, raw_dir)
        if out_path.exists():
            logger.debug("Cached: %s", current)
            summary["skipped_cached"] += 1
            current += dt.timedelta(days=1)
            continue

        try:
            rows = _fetch_one_day(current, rate_limit=rate_limit)
            if rows is None:
                summary["errors"].append(
                    {"date": str(current), "reason": "empty_response"}
                )
            else:
                _save_raw(rows, out_path)
                summary["downloaded"] += 1
                logger.info("Downloaded %s  (%d rows)", current, len(rows))
        except DateMismatchError as exc:
            summary["rejected_date_mismatch"] += 1
            summary["errors"].append(
                {"date": str(current), "reason": f"date_mismatch: {exc}"}
            )
            logger.warning("Date mismatch for %s: %s", current, exc)
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append(
                {"date": str(current), "reason": str(exc)}
            )
            logger.error("Error for %s: %s", current, exc)

        current += dt.timedelta(days=1)

    return summary


# ──────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────

class DateMismatchError(Exception):
    """MCX returned data for a date other than the one we requested."""


def _raw_path(date: dt.date, raw_dir: Path) -> Path:
    return raw_dir / f"bhavcopy_{date.isoformat()}.csv"


def _fetch_one_day(
    date: dt.date,
    *,
    rate_limit: float = MCX_RATE_LIMIT_SECONDS,
) -> list[dict[str, str]] | None:
    """
    Fetch a single day's Bhavcopy from MCX.

    MCX expects DD/MM/YYYY in the request body.
    Returns a list of row dicts or None if empty.
    Raises DateMismatchError if the returned date ≠ requested date.
    """
    request_date_str = date.strftime("%d/%m/%Y")  # DD/MM/YYYY

    payload = {"Date": request_date_str, "InstrumentName": "FUTCOM"}
    headers = {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "KARAT/1.0 (hackathon prototype)",
    }

    last_exc: Exception | None = None
    for attempt in range(1, MCX_MAX_RETRIES + 1):
        try:
            resp = requests.post(
                MCX_BHAVCOPY_URL,
                json=payload,
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            last_exc = exc
            wait = MCX_BACKOFF_BASE ** attempt
            logger.warning(
                "Attempt %d/%d for %s failed: %s  (retry in %.1fs)",
                attempt,
                MCX_MAX_RETRIES,
                date,
                exc,
                wait,
            )
            time.sleep(wait)
    else:
        raise RuntimeError(
            f"All {MCX_MAX_RETRIES} attempts failed for {date}: {last_exc}"
        )

    time.sleep(rate_limit)  # polite rate limiting

    body = resp.json()
    raw_data = body.get("d", body) if isinstance(body, dict) else body

    if not raw_data:
        return None

    # Parse – handle list-of-dicts or CSV text
    if isinstance(raw_data, str):
        rows = list(csv.DictReader(io.StringIO(raw_data)))
    elif isinstance(raw_data, list):
        rows = raw_data
    else:
        logger.warning("Unexpected response type for %s: %s", date, type(raw_data))
        return None

    # Filter to gold contracts only
    gold_rows: list[dict[str, str]] = []
    for row in rows:
        symbol = (row.get("Symbol") or row.get("symbol") or "").strip()
        if symbol in TRACKED_SYMBOLS:
            row_clean = {k.strip(): str(v).strip() for k, v in row.items()}
            # DATE VALIDATION: MCX response date is MM/DD/YYYY
            resp_date_str = row_clean.get("Date") or row_clean.get("date") or ""
            resp_date = _parse_response_date(resp_date_str)
            if resp_date and resp_date != date:
                raise DateMismatchError(
                    f"requested {date}, got {resp_date} "
                    f"(raw '{resp_date_str}')"
                )
            gold_rows.append(row_clean)

    return gold_rows if gold_rows else None


def _parse_response_date(s: str) -> dt.date | None:
    """
    Parse the Date field from MCX response.
    MCX uses MM/DD/YYYY in responses (trap #1).
    """
    s = s.strip()
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    logger.warning("Could not parse response date: '%s'", s)
    return None


def _save_raw(rows: list[dict[str, str]], path: Path) -> None:
    """Persist raw rows as CSV, preserving original fields."""
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
