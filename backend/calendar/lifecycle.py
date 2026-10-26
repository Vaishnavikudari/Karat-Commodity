"""
KARAT – Module 4: Contract Lifecycle & Calendar Engine.

Tracks institutional lifecycle milestones for MCX gold contracts:
1. Listing date & first liquid trading day
2. Staggered tender notice period (compulsory delivery window, 5 trading days prior to expiry)
3. Last trading day & contract expiry
4. Roll window recommendation
5. Trade validation: rejects or flags entries/exits outside valid calendar constraints.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd

from backend.config import CONTRACTS, TRACKED_SYMBOLS, VOLUME_THIN_THRESHOLD, OI_THIN_THRESHOLD


def get_contract_calendar(df: pd.DataFrame) -> dict[str, Any]:
    """
    Extract all distinct contract expiries observed in the dataset,
    augmenting them with institutional trading rules, tender periods,
    and roll windows.
    """
    entries = []
    grouped = df.groupby(["Symbol", "ExpiryDate"])

    for (sym, exp), group in grouped:
        if sym not in CONTRACTS:
            continue
        spec = CONTRACTS[sym]
        exp_date = exp.date() if hasattr(exp, "date") else exp

        first_seen = group["Date"].min()
        last_seen = group["Date"].max()

        first_seen_date = first_seen.date() if hasattr(first_seen, "date") else first_seen
        last_seen_date = last_seen.date() if hasattr(last_seen, "date") else last_seen

        # First liquid day: first date where volume >= VOLUME_THIN_THRESHOLD and OI >= OI_THIN_THRESHOLD
        liquid_days = group[
            (group["Volume"] >= VOLUME_THIN_THRESHOLD) & (group["OpenInterest"] >= OI_THIN_THRESHOLD)
        ]["Date"].sort_values()

        if not liquid_days.empty:
            first_liquid = liquid_days.iloc[0]
            first_liquid_date = first_liquid.date() if hasattr(first_liquid, "date") else first_liquid
        else:
            first_liquid_date = first_seen_date

        # MCX tender notice period begins 5 trading days (~7 calendar days) before expiry
        tender_start = exp_date - dt.timedelta(days=7)
        last_trading_day = exp_date
        # Optimal roll window: 12 to 7 calendar days before expiry
        roll_window_start = exp_date - dt.timedelta(days=12)
        roll_window_end = exp_date - dt.timedelta(days=7)

        total_volume = int(group["Volume"].sum()) if "Volume" in group.columns else 0
        max_oi = int(group["OpenInterest"].max()) if "OpenInterest" in group.columns else 0

        listing_date = spec.listing_start or str(first_seen_date)

        entries.append({
            "symbol": sym,
            "expiry_date": str(exp_date),
            "lot_size_g": spec.lot_size_g,
            "purity": spec.purity,
            "listing_date": listing_date,
            "first_trading_day": str(first_seen_date),
            "first_liquid_day": str(first_liquid_date),
            "last_active_day": str(last_seen_date),
            "roll_window_start": str(roll_window_start),
            "roll_window_end": str(roll_window_end),
            "tender_start": str(tender_start),
            "last_trading_day": str(last_trading_day),
            "total_observed_volume": total_volume,
            "peak_open_interest": max_oi,
            "status": "active" if last_seen_date >= (dt.date.today() - dt.timedelta(days=180)) else "matured",
            "lifecycle_rule": f"Tender notice starts on {tender_start}. Roll positions before {roll_window_end}.",
        })

    entries = sorted(entries, key=lambda x: (x["expiry_date"], x["symbol"]))

    return {
        "events": entries,
        "rules": [
            "All physical delivery settlement notices trigger during the tender period (5 trading days prior to expiry).",
            "Trading algorithm strictly requires exiting or rolling spread positions before tender notice window.",
            "GOLDTEN series trading history commences from 2025 onwards.",
            "Settlement prices are official marks, not executable fills during illiquid roll windows.",
        ],
    }


def validate_trade_calendar(
    symbol: str,
    expiry_date: dt.date | str,
    entry_date: dt.date | str,
    exit_date: dt.date | str,
) -> dict[str, Any]:
    """
    Validate that an intended trade entry and exit fall inside the legal calendar
    for the contract held. Flags or rejects trades that breach lifecycle rules.
    """
    if isinstance(expiry_date, str):
        expiry_date = dt.date.fromisoformat(expiry_date[:10])
    if isinstance(entry_date, str):
        entry_date = dt.date.fromisoformat(entry_date[:10])
    if isinstance(exit_date, str):
        exit_date = dt.date.fromisoformat(exit_date[:10])

    spec = CONTRACTS.get(symbol)
    listing_date = None
    if spec and spec.listing_start:
        listing_date = dt.date.fromisoformat(spec.listing_start)

    tender_start = expiry_date - dt.timedelta(days=7)
    last_trading_day = expiry_date

    is_valid = True
    violations = []

    # 1. Check listing bounds
    if listing_date and entry_date < listing_date:
        is_valid = False
        violations.append(f"Entry {entry_date} precedes listing start {listing_date} for {symbol}.")

    # 2. Sequence check
    if exit_date < entry_date:
        is_valid = False
        violations.append(f"Exit {exit_date} is before entry {entry_date}.")

    # 3. Tender period check
    if entry_date >= tender_start:
        is_valid = False
        violations.append(f"Entry {entry_date} falls inside tender delivery period starting {tender_start}.")

    # 4. Expiry / Last trade day check
    if exit_date > last_trading_day:
        is_valid = False
        violations.append(f"Exit {exit_date} is after contract last trade date {last_trading_day}.")

    is_in_tender = exit_date >= tender_start
    if is_in_tender:
        violations.append(f"Warning: Position held into tender period ({tender_start} to {last_trading_day}).")

    return {
        "symbol": symbol,
        "expiry_date": str(expiry_date),
        "entry_date": str(entry_date),
        "exit_date": str(exit_date),
        "tender_start": str(tender_start),
        "last_trading_day": str(last_trading_day),
        "is_valid": is_valid,
        "held_in_tender": is_in_tender,
        "violations": violations,
    }


def get_upcoming_expiries_and_roll_windows(
    df: pd.DataFrame,
    as_of_date: dt.date | None = None,
) -> list[dict[str, Any]]:
    """
    Returns upcoming contract expiries relative to as_of_date,
    showing remaining days to roll window and tender period.
    """
    calendar_res = get_contract_calendar(df)
    events = calendar_res["events"]

    if as_of_date is None:
        dates = pd.to_datetime(df["Date"]).dropna()
        as_of_date = dates.max().date() if not dates.empty else dt.date.today()

    upcoming = []
    for ev in events:
        exp_d = dt.date.fromisoformat(ev["expiry_date"])
        tender_d = dt.date.fromisoformat(ev["tender_start"])
        roll_d = dt.date.fromisoformat(ev["roll_window_start"])

        if exp_d >= as_of_date:
            days_to_expiry = (exp_d - as_of_date).days
            days_to_tender = (tender_d - as_of_date).days
            days_to_roll = (roll_d - as_of_date).days

            upcoming.append({
                **ev,
                "days_to_expiry": days_to_expiry,
                "days_to_tender": days_to_tender,
                "days_to_roll": days_to_roll,
                "in_roll_window": days_to_roll <= 0 <= days_to_tender,
                "in_tender_period": days_to_tender <= 0 <= days_to_expiry,
            })

    return upcoming
