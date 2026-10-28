"""
KARAT – Term Structure & Forward Carry Analytics.

Analyzes the gold forward curve across different expiry maturities.
Distinguishes mechanical roll-down from genuine relative-value dislocations.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pandas as pd

from backend.config import CONTRACTS, TRACKED_SYMBOLS
from backend.analytics.normaliser import normalise_dataframe


def get_term_structure(
    df: pd.DataFrame,
    date: dt.date | None = None,
    symbol: str | None = None,
) -> dict[str, Any]:
    """
    Compute term structure curves for each contract across available expiries.
    """
    df = normalise_dataframe(df)

    if date is None:
        date = df["Date"].max()
    target_date = pd.Timestamp(date)

    day_df = df[df["Date"] == target_date].copy()
    if day_df.empty:
        dates = df["Date"].sort_values().unique()
        if len(dates) == 0:
            return {"date": str(date), "curves": [], "pairs": []}
        closest_idx = np.argmin(np.abs(dates - target_date))
        target_date = dates[closest_idx]
        day_df = df[df["Date"] == target_date].copy()

    curves: list[dict[str, Any]] = []

    symbols_to_process = [symbol] if (symbol and symbol in TRACKED_SYMBOLS) else TRACKED_SYMBOLS

    for sym in symbols_to_process:
        spec = CONTRACTS[sym]
        sub = day_df[day_df["Symbol"] == sym].sort_values("ExpiryDate")
        if sub.empty:
            continue

        points = []
        near_norm = None
        near_expiry = None

        for idx, row in sub.iterrows():
            exp = row["ExpiryDate"]
            exp_date = exp.date() if hasattr(exp, "date") else exp
            curr_date = target_date.date() if hasattr(target_date, "date") else target_date
            days_to_expiry = max((exp_date - curr_date).days, 0)

            norm_price = float(row["NormalisedPrice"])
            raw_price = float(row["Close"])
            vol = int(row.get("Volume", 0)) if pd.notna(row.get("Volume")) else 0
            oi = int(row.get("OpenInterest", 0)) if pd.notna(row.get("OpenInterest")) else 0

            if near_norm is None:
                near_norm = norm_price
                near_expiry = exp_date


            if near_norm and days_to_expiry > 0 and exp_date != near_expiry:
                cal_days = (exp_date - near_expiry).days
                if cal_days > 0:
                    raw_diff = norm_price - near_norm
                    carry_annualized_pct = ((raw_diff / near_norm) * (365.0 / cal_days)) * 100
                else:
                    carry_annualized_pct = 0.0
            else:
                carry_annualized_pct = 0.0

            points.append({
                "expiry": str(exp_date),
                "days_to_expiry": days_to_expiry,
                "raw_price": raw_price,
                "normalised_price": round(norm_price, 2),
                "volume": vol,
                "open_interest": oi,
                "annualized_carry_pct": round(carry_annualized_pct, 2),
                "is_near_month": (exp_date == near_expiry),
            })

        curves.append({
            "symbol": sym,
            "lot_size_g": spec.lot_size_g,
            "quote_base_g": spec.quote_base_g,
            "purity": spec.purity,
            "points": points,
        })

    regimes = compute_historical_curve_regimes(df, symbol=symbol or "GOLDM")

    return {
        "as_of_date": str(target_date.date()) if hasattr(target_date, "date") else str(target_date),
        "curves": curves,
        "historical_regimes": regimes,
        "disclaimer": "Carry adjustment is an approximation based on calendar days, not a guaranteed forward rate.",
    }


def compute_historical_curve_regimes(
    df: pd.DataFrame,
    symbol: str = "GOLDM",
) -> list[dict[str, Any]]:
    """
    Tracks the historical term structure slope and regimes over time.
    Separates mechanical roll-down from genuine contango / backwardation regimes.
    """
    df = normalise_dataframe(df)
    sub = df[df["Symbol"] == symbol].copy()
    if sub.empty:
        return []

    regimes: list[dict[str, Any]] = []

    dates = sorted(sub["Date"].unique())

    for d in dates:
        group = sub[sub["Date"] == d]
        expiries = group.sort_values("ExpiryDate")
        if len(expiries) < 2:
            continue

        near = expiries.iloc[0]
        far = expiries.iloc[1]

        near_exp = near["ExpiryDate"].date() if hasattr(near["ExpiryDate"], "date") else near["ExpiryDate"]
        far_exp = far["ExpiryDate"].date() if hasattr(far["ExpiryDate"], "date") else far["ExpiryDate"]
        curr_d = d.date() if hasattr(d, "date") else d

        cal_days = (far_exp - near_exp).days
        if cal_days <= 0:
            continue

        raw_near = float(near["Close"])
        raw_far = float(far["Close"])
        norm_near = float(near["NormalisedPrice"])
        norm_far = float(far["NormalisedPrice"])

        spread_bps = ((norm_far - norm_near) / norm_near) * 10000.0 if norm_near > 0 else 0.0
        annualized_carry_pct = (
            ((norm_far - norm_near) / norm_near) * (365.0 / cal_days) * 100.0
            if norm_near > 0 else 0.0
        )

        if annualized_carry_pct > 1.0:
            regime = "Contango"
        elif annualized_carry_pct < -1.0:
            regime = "Backwardation"
        else:
            regime = "Flat / Parity"

        regimes.append({
            "date": str(curr_d),
            "symbol": symbol,
            "near_expiry": str(near_exp),
            "far_expiry": str(far_exp),
            "calendar_days": cal_days,
            "near_norm_price": round(norm_near, 2),
            "far_norm_price": round(norm_far, 2),
            "raw_near_price": raw_near,
            "raw_far_price": raw_far,
            "calendar_spread_bps": round(spread_bps, 2),
            "annualized_carry_pct": round(annualized_carry_pct, 2),
            "regime": regime,
        })

    return regimes
