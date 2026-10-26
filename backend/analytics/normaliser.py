"""
KARAT – price normaliser.

Normalizes MCX gold futures prices to a common ₹/gram basis at 999 purity,
enabling apples-to-apples comparison across contracts with different lot sizes,
quote bases, and purities.

Formula:
    normalized_price = (raw_price / quote_base_g) * (999 / purity)

Example:
    GOLDM quoted ₹58,650 per 10g at 995 purity
    = ₹5,865/g raw
    = ₹5,865 × (999/995) = ₹5,888.55/g at 999 purity
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd
import numpy as np

from backend.config import CONTRACTS, ContractSpec, TRACKED_SYMBOLS


def normalise_price(raw_price: float, spec: ContractSpec) -> float:
    """Normalise a single raw price to ₹/gram at 999 purity."""
    if raw_price <= 0 or spec.quote_base_g <= 0:
        return 0.0
    per_gram = raw_price / spec.quote_base_g
    return per_gram * (999 / spec.purity)


def normalise_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add normalised price columns to the dataframe.

    Adds:
        - PricePerGram: raw_price / quote_base_g
        - NormalisedPrice: ₹/gram at 999 purity
    """
    df = df.copy()
    df["PricePerGram"] = 0.0
    df["NormalisedPrice"] = 0.0

    for symbol, spec in CONTRACTS.items():
        mask = df["Symbol"] == symbol
        if mask.any():
            df.loc[mask, "PricePerGram"] = df.loc[mask, "Close"] / spec.quote_base_g
            df.loc[mask, "NormalisedPrice"] = (
                df.loc[mask, "PricePerGram"] * (999 / spec.purity)
            )

    return df


def get_normalised_snapshot(
    df: pd.DataFrame,
    date: dt.date | None = None,
    reference_symbol: str = "GOLDTEN",
) -> list[dict[str, Any]]:
    """
    Get normalised prices for all contracts on a given date.

    Returns a list of dicts with premium/discount vs reference.
    If date is None, uses the latest available date.
    """
    df = normalise_dataframe(df)

    if date is None:
        date = df["Date"].max()

    target_date = pd.Timestamp(date)
    day_df = df[df["Date"] == target_date]

    if day_df.empty:
        # Fall back to closest available date
        dates = df["Date"].sort_values().unique()
        if len(dates) == 0:
            return []
        closest_idx = np.argmin(np.abs(dates - target_date))
        target_date = dates[closest_idx]
        day_df = df[df["Date"] == target_date]

    # For each symbol, pick the nearest-expiry contract (most liquid)
    results = []
    ref_norm_price = None

    # First pass: find reference price
    for symbol in TRACKED_SYMBOLS:
        sym_df = day_df[day_df["Symbol"] == symbol].copy()
        if sym_df.empty:
            continue
        # Pick nearest expiry
        sym_df = sym_df.sort_values("ExpiryDate")
        row = sym_df.iloc[0]
        if symbol == reference_symbol:
            ref_norm_price = row["NormalisedPrice"]
            break

    # If reference not found, use first available
    if ref_norm_price is None or ref_norm_price == 0:
        for symbol in TRACKED_SYMBOLS:
            sym_df = day_df[day_df["Symbol"] == symbol]
            if not sym_df.empty:
                row = sym_df.sort_values("ExpiryDate").iloc[0]
                if row["NormalisedPrice"] > 0:
                    ref_norm_price = row["NormalisedPrice"]
                    reference_symbol = symbol
                    break

    if ref_norm_price is None or ref_norm_price == 0:
        ref_norm_price = 1.0  # Avoid division by zero

    # Second pass: build results
    for symbol in TRACKED_SYMBOLS:
        spec = CONTRACTS[symbol]
        sym_df = day_df[day_df["Symbol"] == symbol].copy()

        entry: dict[str, Any] = {
            "symbol": symbol,
            "lot_size_g": spec.lot_size_g,
            "quote_base_g": spec.quote_base_g,
            "purity": spec.purity,
            "expiry_window": spec.expiry_window,
            "listing_start": spec.listing_start,
            "notes": spec.notes,
        }

        if sym_df.empty:
            entry.update({
                "raw_price": None,
                "expiry_date": None,
                "price_per_gram": None,
                "normalised_price": None,
                "premium_vs_ref": None,
                "premium_bps": None,
                "volume": None,
                "open_interest": None,
                "liquidity_status": "unavailable",
                "daily_change": None,
                "daily_change_pct": None,
            })
        else:
            sym_df = sym_df.sort_values("ExpiryDate")
            row = sym_df.iloc[0]

            norm_price = row["NormalisedPrice"]
            premium = norm_price - ref_norm_price
            premium_bps = (premium / ref_norm_price) * 10000 if ref_norm_price else 0

            volume = row.get("Volume", 0)
            oi = row.get("OpenInterest", 0)

            from backend.config import VOLUME_THIN_THRESHOLD, OI_THIN_THRESHOLD
            if volume == 0 and oi == 0:
                liquidity = "unavailable"
            elif volume < VOLUME_THIN_THRESHOLD or oi < OI_THIN_THRESHOLD:
                liquidity = "thin"
            else:
                liquidity = "liquid"

            # Try to compute daily change
            prev_dates = df[
                (df["Symbol"] == symbol)
                & (df["Date"] < target_date)
            ]["Date"].unique()
            daily_change = None
            daily_change_pct = None
            if len(prev_dates) > 0:
                prev_date = max(prev_dates)
                prev_row = df[
                    (df["Symbol"] == symbol)
                    & (df["Date"] == prev_date)
                ].sort_values("ExpiryDate")
                if not prev_row.empty:
                    prev_close = prev_row.iloc[0]["Close"]
                    if prev_close > 0:
                        daily_change = row["Close"] - prev_close
                        daily_change_pct = (daily_change / prev_close) * 100

            entry.update({
                "raw_price": float(row["Close"]),
                "expiry_date": str(row["ExpiryDate"].date()) if hasattr(row["ExpiryDate"], "date") else str(row["ExpiryDate"]),
                "price_per_gram": round(float(row["PricePerGram"]), 2),
                "normalised_price": round(float(norm_price), 2),
                "premium_vs_ref": round(float(premium), 2),
                "premium_bps": round(float(premium_bps), 2),
                "volume": int(volume) if pd.notna(volume) else None,
                "open_interest": int(oi) if pd.notna(oi) else None,
                "liquidity_status": liquidity,
                "daily_change": round(float(daily_change), 2) if daily_change is not None else None,
                "daily_change_pct": round(float(daily_change_pct), 4) if daily_change_pct is not None else None,
            })

        results.append(entry)

    return results


def get_sparkline_data(
    df: pd.DataFrame,
    symbol: str,
    days: int = 30,
) -> list[dict[str, Any]]:
    """Get recent close prices for a mini sparkline chart."""
    df = normalise_dataframe(df)
    sym_df = df[df["Symbol"] == symbol].copy()

    if sym_df.empty:
        return []

    # For each date, pick the nearest-expiry contract
    latest_dates = sym_df["Date"].sort_values().unique()[-days:]
    points = []
    for d in latest_dates:
        day_rows = sym_df[sym_df["Date"] == d].sort_values("ExpiryDate")
        if not day_rows.empty:
            row = day_rows.iloc[0]
            points.append({
                "date": str(d.date()) if hasattr(d, "date") else str(d),
                "close": float(row["Close"]),
                "normalised": round(float(row["NormalisedPrice"]), 2),
            })

    return points
