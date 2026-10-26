"""
KARAT – spread analytics & z-score engine.

Computes inter-contract spreads in ₹/gram and basis points,
rolling z-scores, and carry-adjusted spreads.

Key design decisions:
- Spread = normalised_price(leg_A) - normalised_price(leg_B)
- Z-score uses a rolling window (default 20 trading days)
- Carry adjustment approximates time-value differences between expiries
- Thin-liquidity days are flagged but NOT excluded from calculations
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pandas as pd

from backend.config import (
    CONTRACTS,
    TRACKED_SYMBOLS,
    ZSCORE_WINDOW,
    ENTRY_Z,
    EXIT_Z,
    VOLUME_THIN_THRESHOLD,
    OI_THIN_THRESHOLD,
    DEFAULT_COST_PER_LEG_BPS,
    TOTAL_LEGS_PER_ROUND_TRIP,
    THIN_LIQUIDITY_SLIPPAGE_MULT,
)
from backend.analytics.normaliser import normalise_dataframe


def _select_benchmark_contract(sub: pd.DataFrame) -> pd.Series:
    """
    Select the active, liquid benchmark contract for spread computation.
    Avoids contracts currently in their final 3-day tender window when
    the next active contract has already absorbed primary liquidity.
    """
    if len(sub) == 1:
        return sub.iloc[0]
    if "ExpiryDate" in sub.columns and "Date" in sub.columns:
        diff_days = (pd.to_datetime(sub["ExpiryDate"]) - pd.to_datetime(sub["Date"])).dt.days
        valid = sub[diff_days > 3]
        if not valid.empty:
            if "Volume" in valid.columns:
                return valid.sort_values("Volume", ascending=False).iloc[0]
            return valid.sort_values("ExpiryDate").iloc[0]
    if "Volume" in sub.columns:
        return sub.sort_values("Volume", ascending=False).iloc[0]
    return sub.sort_values("ExpiryDate").iloc[0]


def compute_spread_series(
    df: pd.DataFrame,
    symbol_a: str = "GOLDM",
    symbol_b: str = "GOLDTEN",
    window: int = ZSCORE_WINDOW,
    use_carry_adj: bool = False,
) -> pd.DataFrame:
    """
    Compute the spread time series between two contracts.

    For each date, picks the active benchmark row for each symbol,
    normalises both, and computes spread metrics.

    Returns a DataFrame indexed by date with columns:
        date, norm_a, norm_b, spread_rupees, spread_bps,
        carry_adjusted_spread_bps, z_score, carry_adjusted_z_score,
        vol_a, vol_b, oi_a, oi_b, liquidity_a, liquidity_b, thin_day
    """
    df = normalise_dataframe(df)

    # Get common dates
    dates_a = set(df[df["Symbol"] == symbol_a]["Date"].unique())
    dates_b = set(df[df["Symbol"] == symbol_b]["Date"].unique())
    common_dates = sorted(dates_a & dates_b)

    if not common_dates:
        return pd.DataFrame()

    records = []
    for d in common_dates:
        sub_a = df[(df["Symbol"] == symbol_a) & (df["Date"] == d)]
        sub_b = df[(df["Symbol"] == symbol_b) & (df["Date"] == d)]
        row_a = _select_benchmark_contract(sub_a)
        row_b = _select_benchmark_contract(sub_b)

        norm_a = row_a["NormalisedPrice"]
        norm_b = row_b["NormalisedPrice"]
        spread = norm_a - norm_b

        # Exact formula: spread_bps(a, b) = (norm_a - norm_b) / norm_b * 10000
        spread_bps = ((norm_a - norm_b) / norm_b * 10000) if norm_b > 0 else 0.0

        # Term structure carry adjustment (approximate mechanical roll-down)
        exp_a = row_a["ExpiryDate"].date() if hasattr(row_a["ExpiryDate"], "date") else row_a["ExpiryDate"]
        exp_b = row_b["ExpiryDate"].date() if hasattr(row_b["ExpiryDate"], "date") else row_b["ExpiryDate"]
        curr_d = d.date() if hasattr(d, "date") else d
        days_diff = (exp_a - exp_b).days
        # Approx 6% annual MCX financing/carry curve
        carry_adj_bps = (600.0 * (days_diff / 365.0))
        carry_adjusted_spread_bps = spread_bps - carry_adj_bps

        vol_a = int(row_a.get("Volume", 0)) if pd.notna(row_a.get("Volume", 0)) else 0
        vol_b = int(row_b.get("Volume", 0)) if pd.notna(row_b.get("Volume", 0)) else 0
        oi_a = int(row_a.get("OpenInterest", 0)) if pd.notna(row_a.get("OpenInterest", 0)) else 0
        oi_b = int(row_b.get("OpenInterest", 0)) if pd.notna(row_b.get("OpenInterest", 0)) else 0

        liq_a = "thin" if (vol_a < VOLUME_THIN_THRESHOLD or oi_a < OI_THIN_THRESHOLD) else "liquid"
        liq_b = "thin" if (vol_b < VOLUME_THIN_THRESHOLD or oi_b < OI_THIN_THRESHOLD) else "liquid"

        records.append({
            "date": d,
            "norm_a": round(float(norm_a), 2),
            "norm_b": round(float(norm_b), 2),
            "raw_a": float(row_a["Close"]),
            "raw_b": float(row_b["Close"]),
            "spread_rupees": round(float(spread), 2),
            "spread_bps": round(float(spread_bps), 2),
            "carry_adjusted_spread_bps": round(float(carry_adjusted_spread_bps), 2),
            "vol_a": vol_a,
            "vol_b": vol_b,
            "oi_a": oi_a,
            "oi_b": oi_b,
            "liquidity_a": liq_a,
            "liquidity_b": liq_b,
            "thin_day": liq_a == "thin" or liq_b == "thin",
            "expiry_a": str(exp_a),
            "expiry_b": str(exp_b),
        })

    result = pd.DataFrame(records)

    # Rolling z-score using strictly PRIOR observations (zero contemporaneous/lookahead bias)
    # Day t's z-score evaluates day t's spread against the mean and std of prior days strictly before t
    if len(result) >= window + 1:
        shifted_spread = result["spread_bps"].shift(1)
        rolling_mean = shifted_spread.rolling(window=window, min_periods=window).mean()
        rolling_std = shifted_spread.rolling(window=window, min_periods=window).std()
        raw_z = np.where(
            rolling_std > 0,
            (result["spread_bps"] - rolling_mean) / rolling_std,
            0.0,
        )
        result["raw_z_score"] = np.nan_to_num(raw_z, nan=0.0).round(4)

        # Carry-adjusted rolling Z-score (removes mechanical roll-down baseline drift)
        shifted_carry = result["carry_adjusted_spread_bps"].shift(1)
        rolling_carry_mean = shifted_carry.rolling(window=window, min_periods=window).mean()
        rolling_carry_std = shifted_carry.rolling(window=window, min_periods=window).std()
        carry_z = np.where(
            rolling_carry_std > 0,
            (result["carry_adjusted_spread_bps"] - rolling_carry_mean) / rolling_carry_std,
            0.0,
        )
        result["carry_adjusted_z_score"] = np.nan_to_num(carry_z, nan=0.0).round(4)

        if use_carry_adj:
            result["z_score"] = result["carry_adjusted_z_score"]
        else:
            result["z_score"] = result["raw_z_score"]
    else:
        result["raw_z_score"] = 0.0
        result["carry_adjusted_z_score"] = 0.0
        result["z_score"] = 0.0

    return result


def estimate_round_trip_cost(
    cost_per_leg_bps: float = DEFAULT_COST_PER_LEG_BPS,
    thin_day: bool = False,
) -> float:
    """Estimate total round-trip cost in basis points."""
    base = cost_per_leg_bps * TOTAL_LEGS_PER_ROUND_TRIP
    if thin_day:
        base *= THIN_LIQUIDITY_SLIPPAGE_MULT
    return round(base, 2)


def get_spread_summary(
    df: pd.DataFrame,
    symbol_a: str = "GOLDM",
    symbol_b: str = "GOLDTEN",
    window: int = ZSCORE_WINDOW,
    cost_per_leg_bps: float = DEFAULT_COST_PER_LEG_BPS,
) -> dict[str, Any]:
    """Get a summary of the current spread state."""
    spread_df = compute_spread_series(df, symbol_a, symbol_b, window)

    if spread_df.empty:
        return {
            "symbol_a": symbol_a,
            "symbol_b": symbol_b,
            "data_available": False,
        }

    latest = spread_df.iloc[-1]
    thin = bool(latest["thin_day"])
    rt_cost = estimate_round_trip_cost(cost_per_leg_bps, thin)

    return {
        "symbol_a": symbol_a,
        "symbol_b": symbol_b,
        "data_available": True,
        "date": str(latest["date"].date()) if hasattr(latest["date"], "date") else str(latest["date"]),
        "spread_rupees": latest["spread_rupees"],
        "spread_bps": latest["spread_bps"],
        "carry_adjusted_spread_bps": float(latest.get("carry_adjusted_spread_bps", latest["spread_bps"])),
        "z_score": latest["z_score"],
        "carry_adjusted_z_score": float(latest.get("carry_adjusted_z_score", latest["z_score"])),
        "norm_a": latest["norm_a"],
        "norm_b": latest["norm_b"],
        "liquidity_a": latest["liquidity_a"],
        "liquidity_b": latest["liquidity_b"],
        "thin_day": thin,
        "estimated_rt_cost_bps": rt_cost,
        "breakeven_spread_bps": rt_cost,
        "total_observations": len(spread_df),
        "window": window,
    }


def get_spread_chart_data(
    df: pd.DataFrame,
    symbol_a: str = "GOLDM",
    symbol_b: str = "GOLDTEN",
    window: int = ZSCORE_WINDOW,
) -> list[dict[str, Any]]:
    """Get spread time series formatted for chart rendering."""
    spread_df = compute_spread_series(df, symbol_a, symbol_b, window)

    if spread_df.empty:
        return []

    records = []
    for _, row in spread_df.iterrows():
        records.append({
            "date": str(row["date"].date()) if hasattr(row["date"], "date") else str(row["date"]),
            "spread_bps": row["spread_bps"],
            "spread_rupees": row["spread_rupees"],
            "carry_adjusted_spread_bps": float(row.get("carry_adjusted_spread_bps", row["spread_bps"])),
            "z_score": row["z_score"],
            "carry_adjusted_z_score": float(row.get("carry_adjusted_z_score", row["z_score"])),
            "norm_a": row["norm_a"],
            "norm_b": row["norm_b"],
            "thin_day": bool(row["thin_day"]),
            "vol_a": row["vol_a"],
            "vol_b": row["vol_b"],
        })

    return records
