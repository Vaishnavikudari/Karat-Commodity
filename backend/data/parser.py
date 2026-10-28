"""
KARAT – raw → clean parser.

Reads raw Bhavcopy CSVs, applies cleaning, and produces a single
Parquet file keyed by (symbol, expiry_date, date).

IDENTITY RULE: every row is identified by (symbol, expiry_date).
We NEVER build a continuous near-month series because that creates
artificial jumps at expiry.

FORMAT TRAPS HANDLED
- ExpiryDate like "04SEP2026" → datetime.date
- Symbol space-padding → stripped
- Response Date in MM/DD/YYYY → parsed
- Encoding quirks → utf-8-sig fallback
"""

from __future__ import annotations

import csv
import datetime as dt
import logging
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.config import (
    CLEAN_DIR,
    PARQUET_PATH,
    RAW_DIR,
    SAMPLE_DIR,
    TRACKED_SYMBOLS,
)

logger = logging.getLogger(__name__)


_MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

_EXPIRY_RE = re.compile(r"^(\d{2})([A-Z]{3})(\d{4})$")


def parse_expiry_date(s: str) -> dt.date | None:
    """
    Parse MCX expiry strings like '04SEP2026' → date(2026, 9, 4).
    Also handles ISO and slash-separated formats as fallback.
    """
    s = s.strip().upper()
    if not s:
        return None

    m = _EXPIRY_RE.match(s)
    if m:
        day, mon_str, year = int(m.group(1)), m.group(2), int(m.group(3))
        month = _MONTH_MAP.get(mon_str)
        if month:
            try:
                return dt.date(year, month, day)
            except ValueError:
                pass


    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    logger.warning("Cannot parse expiry date: '%s'", s)
    return None


def parse_response_date(s: str) -> dt.date | None:
    """Parse the trade-date field (MM/DD/YYYY from MCX, ISO from sample)."""
    s = s.strip()
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%m-%d-%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    logger.warning("Cannot parse trade date: '%s'", s)
    return None


_NUMERIC_COLS = ["Open", "High", "Low", "Close", "Volume", "OpenInterest"]


def _clean_file(path: Path) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """
    Read one raw CSV and return (clean_df, rejection_log).

    Rejections are logged with reason but rows are NOT silently dropped:
    price-outlier rows are flagged rather than removed.
    """
    rejections: list[dict[str, Any]] = []


    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(path, encoding=enc, dtype=str)
            break
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    else:
        rejections.append({"file": path.name, "reason": "unreadable_encoding", "count": 1})
        return pd.DataFrame(), rejections

    if df.empty:
        return pd.DataFrame(), rejections

    raw_row_count = len(df)


    df.columns = df.columns.str.strip()

    col_map = {}
    for col in df.columns:
        lc = col.lower().replace(" ", "").replace("_", "")
        if lc == "symbol":
            col_map[col] = "Symbol"
        elif lc in ("date", "tradedate"):
            col_map[col] = "Date"
        elif lc in ("expirydate", "expiry"):
            col_map[col] = "ExpiryDate"
        elif lc == "open":
            col_map[col] = "Open"
        elif lc == "high":
            col_map[col] = "High"
        elif lc == "low":
            col_map[col] = "Low"
        elif lc in ("close", "settle", "settlement"):
            col_map[col] = "Close"
        elif lc in ("volume", "tradedqty"):
            col_map[col] = "Volume"
        elif lc in ("openinterest", "oi"):
            col_map[col] = "OpenInterest"
    df = df.rename(columns=col_map)


    if "Symbol" in df.columns:
        df["Symbol"] = df["Symbol"].str.strip()


    if "Symbol" in df.columns:
        mask = df["Symbol"].isin(TRACKED_SYMBOLS)
        rejected_symbols = df.loc[~mask, "Symbol"].unique().tolist()
        if rejected_symbols:
            rejections.append({
                "file": path.name,
                "reason": "non_gold_symbol",
                "symbols": rejected_symbols,
                "count": int((~mask).sum()),
            })
        df = df.loc[mask].copy()

    if df.empty:
        return pd.DataFrame(), rejections


    if "Date" in df.columns:
        df["Date"] = df["Date"].apply(
            lambda x: parse_response_date(str(x)) if pd.notna(x) else None
        )
        bad_dates = df["Date"].isna()
        if bad_dates.any():
            rejections.append({
                "file": path.name,
                "reason": "unparseable_date",
                "count": int(bad_dates.sum()),
            })
            df = df.loc[~bad_dates].copy()


    file_date_match = re.search(r"bhavcopy_(\d{4}-\d{2}-\d{2})\.csv", path.name)
    if file_date_match and "Date" in df.columns:
        try:
            expected_date = dt.date.fromisoformat(file_date_match.group(1))
            mismatched = df["Date"].apply(lambda d: d is not None and d != expected_date)
            if mismatched.any():
                mismatch_count = int(mismatched.sum())
                rejections.append({
                    "file": path.name,
                    "reason": "date_mismatch",
                    "expected_date": str(expected_date),
                    "count": mismatch_count,
                })
                df = df.loc[~mismatched].copy()
        except ValueError:
            pass

    if "ExpiryDate" in df.columns:
        df["ExpiryDate"] = df["ExpiryDate"].apply(
            lambda x: parse_expiry_date(str(x)) if pd.notna(x) else None
        )
        bad_exp = df["ExpiryDate"].isna()
        if bad_exp.any():
            rejections.append({
                "file": path.name,
                "reason": "unparseable_expiry",
                "count": int(bad_exp.sum()),
            })
            df = df.loc[~bad_exp].copy()

    if df.empty:
        return pd.DataFrame(), rejections


    for col in _NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].str.replace(",", ""), errors="coerce")


    if "Volume" in df.columns:
        df["ZeroVolume"] = df["Volume"] == 0


    df["PriceOutlier"] = False
    if "Close" in df.columns and "Symbol" in df.columns:
        for sym in df["Symbol"].unique():
            mask_sym = df["Symbol"] == sym
            closes = df.loc[mask_sym, "Close"]
            if len(closes) > 1:
                median = closes.median()
                std = closes.std()
                z = ((closes - closes.mean()) / std).abs() if (std is not None and std > 0) else pd.Series(0, index=closes.index)
                ratio_outlier = (closes > 2.0 * median) | (closes < 0.5 * median) if median > 0 else False
                df.loc[mask_sym, "PriceOutlier"] = (z > 3.0) | ratio_outlier

    outlier_count = int(df["PriceOutlier"].sum())
    if outlier_count:
        rejections.append({
            "file": path.name,
            "reason": "price_outlier_flagged",
            "count": outlier_count,
        })

    df.attrs["raw_rows"] = raw_row_count
    return df, rejections


def build_clean_dataset(
    raw_dir: Path = RAW_DIR,
    output_path: Path = PARQUET_PATH,
) -> dict[str, Any]:
    """
    Parse every raw CSV in *raw_dir*, concatenate, deduplicate, sort,
    and write to Parquet.

    Returns a quality report dict.
    """
    raw_files = sorted(raw_dir.glob("bhavcopy_*.csv"))
    if not raw_files:
        logger.warning("No raw files found in %s", raw_dir)
        return {"status": "no_raw_files", "files": 0}

    frames: list[pd.DataFrame] = []
    all_rejections: list[dict[str, Any]] = []
    total_raw_rows = 0

    for fp in raw_files:
        df, rej = _clean_file(fp)
        total_raw_rows += df.attrs.get("raw_rows", len(df))
        all_rejections.extend(rej)
        if not df.empty:
            frames.append(df)

    if not frames:
        return {
            "status": "no_valid_rows",
            "files": len(raw_files),
            "rejections": all_rejections,
        }

    combined = pd.concat(frames, ignore_index=True)


    key_cols = ["Symbol", "ExpiryDate", "Date"]
    before = len(combined)
    combined = combined.drop_duplicates(subset=key_cols, keep="last")
    dupes = before - len(combined)


    combined = combined.sort_values(key_cols).reset_index(drop=True)


    combined["Date"] = pd.to_datetime(combined["Date"])
    combined["ExpiryDate"] = pd.to_datetime(combined["ExpiryDate"])


    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(output_path, index=False, engine="pyarrow")
    logger.info(
        "Wrote %d clean rows to %s", len(combined), output_path
    )


    report = _quality_report(combined, all_rejections, dupes, len(raw_files), raw_rows_loaded=total_raw_rows)
    return report


def _quality_report(
    df: pd.DataFrame,
    rejections: list[dict],
    duplicates_removed: int,
    raw_file_count: int,
    raw_rows_loaded: int = 0,
    source: str = "mcx",
) -> dict[str, Any]:
    """Produce the data-quality summary."""
    zero_vol = int(df["ZeroVolume"].sum()) if "ZeroVolume" in df.columns else 0
    outliers = int(df["PriceOutlier"].sum()) if "PriceOutlier" in df.columns else 0


    missing_day_flags: list[dict] = []
    if "Date" in df.columns and "Symbol" in df.columns:
        for sym in df["Symbol"].unique():
            dates = df.loc[df["Symbol"] == sym, "Date"].drop_duplicates().sort_values()
            if len(dates) < 2:
                continue
            gaps = dates.diff().dt.days
            big_gaps = gaps[gaps > 4]
            for idx in big_gaps.index:
                missing_day_flags.append({
                    "symbol": sym,
                    "from": str(dates.loc[idx - 1] if idx - 1 in dates.index else "?"),
                    "to": str(dates.loc[idx]),
                    "calendar_days": int(gaps.loc[idx]),
                })

    status, last_date = get_data_status(df, source)

    reasons_count: dict[str, int] = {
        "date_mismatch": 0,
        "bad_format": 0,
        "duplicate": duplicates_removed,
        "non_tracked_symbol": 0,
        "price_outlier_flagged": 0,
    }
    for r in rejections:
        reason = r.get("reason", "")
        count = r.get("count", 1)
        if reason == "date_mismatch":
            reasons_count["date_mismatch"] += count
        elif "bad_format" in reason or "unparseable" in reason or "unreadable" in reason:
            reasons_count["bad_format"] += count
        elif reason == "non_gold_symbol":
            reasons_count["non_tracked_symbol"] += count
        elif reason == "price_outlier_flagged":
            reasons_count["price_outlier_flagged"] += count

    return {
        "status": "ok",
        "data_status": status,
        "last_verified_trading_date": last_date,
        "data_source": source,
        "raw_files": raw_file_count,
        "raw_rows_loaded": raw_rows_loaded or len(df),
        "total_rows": len(df),
        "symbols": sorted(df["Symbol"].unique().tolist()) if "Symbol" in df.columns else [],
        "date_range": {
            "min": str(df["Date"].min()) if "Date" in df.columns else None,
            "max": str(df["Date"].max()) if "Date" in df.columns else None,
        },
        "duplicates_removed": duplicates_removed,
        "zero_volume_rows": zero_vol,
        "price_outliers_flagged": outliers,
        "rejections": rejections,
        "rejections_by_reason": reasons_count,
        "missing_trading_days": missing_day_flags,
        "raw_files_cached_untouched": True,
    }


def validate_dataset_purity(df: pd.DataFrame, source: str) -> bool:
    """Ensure dataset strictly contains only real or demo rows, never mixed."""
    if df is None or df.empty:
        return True
    if "_data_source" in df.columns:
        sources = df["_data_source"].unique()
        if len(sources) > 1:
            return False
        if len(sources) == 1 and sources[0] != source:
            return False
    return True


def get_data_status(
    df: pd.DataFrame,
    source: str,
    date: dt.date | str | None = None,
    required_symbols: list[str] | None = None,
) -> tuple[str, str | None]:
    """
    Determine (data_status, last_verified_trading_date).

    data_status:
      - 'real': Live MCX data with verified completeness (all required contracts and no missing days)
      - 'demo': Bundled offline sample dataset
      - 'incomplete': MCX data with missing contracts, gaps in trading days, or missing dates
    last_verified_trading_date:
      ISO date string (YYYY-MM-DD) of the latest verified trading bar, or None.
    """
    if df is None or df.empty or "Date" not in df.columns:
        return "incomplete", None

    if not validate_dataset_purity(df, source):
        return "incomplete", None

    dates = df["Date"].dropna().sort_values()
    if dates.empty:
        return "incomplete", None

    last_val = dates.iloc[-1]
    last_verified_trading_date = (
        str(last_val.date()) if hasattr(last_val, "date") else str(last_val)[:10]
    )

    if source == "sample":
        return "demo", last_verified_trading_date

    if source != "mcx":
        return "incomplete", last_verified_trading_date

    if required_symbols is None:
        required_symbols = list(TRACKED_SYMBOLS)


    if date is not None:
        if isinstance(date, str):
            try:
                target_dt = dt.date.fromisoformat(date)
            except ValueError:
                return "incomplete", last_verified_trading_date
        elif isinstance(date, dt.date):
            target_dt = date
        elif hasattr(date, "date"):
            target_dt = date.date()
        else:
            return "incomplete", last_verified_trading_date

        mask = (
            df["Date"].dt.date == target_dt
            if hasattr(df["Date"].iloc[0], "date")
            else df["Date"] == pd.Timestamp(target_dt)
        )
        date_slice = df.loc[mask]
        if date_slice.empty:
            return "incomplete", last_verified_trading_date

        present_symbols = set(date_slice["Symbol"].unique())

        expected = [
            s for s in required_symbols
            if not (s == "GOLDTEN" and target_dt < dt.date(2025, 4, 1))
        ]
        if not set(expected).issubset(present_symbols):
            return "incomplete", last_verified_trading_date
    else:

        latest_dt = (
            last_val.date()
            if hasattr(last_val, "date")
            else pd.to_datetime(last_val).date()
        )
        mask = (
            df["Date"].dt.date == latest_dt
            if hasattr(df["Date"].iloc[0], "date")
            else df["Date"] == pd.Timestamp(latest_dt)
        )
        latest_slice = df.loc[mask]
        present_symbols = set(latest_slice["Symbol"].unique())
        expected = [
            s for s in required_symbols
            if not (s == "GOLDTEN" and latest_dt < dt.date(2025, 4, 1))
        ]
        if not set(expected).issubset(present_symbols):
            return "incomplete", last_verified_trading_date


    for sym in required_symbols:
        sym_dates = df.loc[df["Symbol"] == sym, "Date"].drop_duplicates().sort_values()
        if len(sym_dates) >= 2:
            gaps = sym_dates.diff().dt.days
            if (gaps > 4).any():
                return "incomplete", last_verified_trading_date

    return "real", last_verified_trading_date


def get_data_quality_report(
    df: pd.DataFrame | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """
    Produce a full data quality report:
    - rows loaded from raw files
    - rejected rows with reasons (date mismatch, bad format, duplicate, non-tracked)
    - missing trading days
    - zero-volume rows
    - flagged price outliers (never silently dropped)
    - cache status (raw files stored untouched)
    """
    if df is None or source is None:
        df, source = load_data()

    data_status, last_verified = get_data_status(df, source)
    zero_vol = int(df["ZeroVolume"].sum()) if "ZeroVolume" in df.columns else 0
    outliers = int(df["PriceOutlier"].sum()) if "PriceOutlier" in df.columns else 0
    symbols = sorted(df["Symbol"].unique().tolist()) if "Symbol" in df.columns else []

    history_by_sym = {}
    for s in symbols:
        sub = df[df["Symbol"] == s]
        history_by_sym[s] = {
            "total_rows": len(sub),
            "expiries_observed": sub["ExpiryDate"].nunique(),
            "first_date": (
                str(sub["Date"].min().date())
                if hasattr(sub["Date"].min(), "date")
                else str(sub["Date"].min())[:10]
            ),
            "last_date": (
                str(sub["Date"].max().date())
                if hasattr(sub["Date"].max(), "date")
                else str(sub["Date"].max())[:10]
            ),
        }

    missing_day_flags: list[dict[str, Any]] = []
    if "Date" in df.columns and "Symbol" in df.columns:
        for sym in symbols:
            dates = df.loc[df["Symbol"] == sym, "Date"].drop_duplicates().sort_values().reset_index(drop=True)
            if len(dates) < 2:
                continue
            gaps = dates.diff().dt.days
            big_gaps = gaps[gaps > 4]
            for idx in big_gaps.index:
                missing_day_flags.append({
                    "symbol": sym,
                    "from": str(
                        dates.loc[idx - 1].date()
                        if hasattr(dates.loc[idx - 1], "date")
                        else str(dates.loc[idx - 1])[:10]
                    ),
                    "to": str(
                        dates.loc[idx].date()
                        if hasattr(dates.loc[idx], "date")
                        else str(dates.loc[idx])[:10]
                    ),
                    "calendar_days": int(gaps.loc[idx]),
                })

    dir_to_scan = RAW_DIR if source == "mcx" else SAMPLE_DIR
    csv_files = sorted(dir_to_scan.glob("*.csv")) if dir_to_scan.exists() else []

    raw_rows_loaded = 0
    rejections_list: list[dict[str, Any]] = []
    for fp in csv_files:
        try:
            for enc in ("utf-8", "utf-8-sig", "latin-1"):
                try:
                    raw_df = pd.read_csv(fp, encoding=enc, dtype=str)
                    raw_rows_loaded += len(raw_df)
                    break
                except Exception:
                    continue
            _, file_rejections = _clean_file(fp)
            rejections_list.extend(file_rejections)
        except Exception:
            pass

    reasons_count: dict[str, int] = {
        "date_mismatch": 0,
        "bad_format": 0,
        "duplicate": 0,
        "non_tracked_symbol": 0,
        "price_outlier_flagged": 0,
    }
    for r in rejections_list:
        reason = r.get("reason", "")
        count = r.get("count", 1)
        if reason == "date_mismatch":
            reasons_count["date_mismatch"] += count
        elif "bad_format" in reason or "unparseable" in reason or "unreadable" in reason:
            reasons_count["bad_format"] += count
        elif reason == "non_gold_symbol":
            reasons_count["non_tracked_symbol"] += count
        elif reason == "price_outlier_flagged":
            reasons_count["price_outlier_flagged"] += count

    if raw_rows_loaded == 0:
        raw_rows_loaded = len(df)

    start_date = (
        str(df["Date"].min().date())
        if hasattr(df["Date"].min(), "date")
        else str(df["Date"].min())[:10]
        if not df.empty
        else None
    )
    end_date = (
        str(df["Date"].max().date())
        if hasattr(df["Date"].max(), "date")
        else str(df["Date"].max())[:10]
        if not df.empty
        else None
    )

    return {
        "data_status": data_status,
        "last_verified_trading_date": last_verified,
        "data_source": source,
        "is_live_mcx": (source == "mcx"),
        "sample_fallback_active": (source == "sample"),
        "total_rows": len(df),
        "total_rows_loaded": raw_rows_loaded,
        "valid_rows": len(df),
        "total_symbols": len(symbols),
        "tracked_symbols": symbols,
        "date_range": {
            "start": start_date,
            "end": end_date,
        },
        "zero_volume_rows": zero_vol,
        "price_outliers_flagged": outliers,
        "duplicates_purged": 0,
        "rejections": rejections_list,
        "rejections_by_reason": reasons_count,
        "missing_trading_days": missing_day_flags,
        "missing_trading_days_count": len(missing_day_flags),
        "contract_coverage": history_by_sym,
        "raw_files_cached_untouched": True,
        "raw_cache_count": len(csv_files),
    }


def load_clean(path: Path = PARQUET_PATH) -> pd.DataFrame:
    """Load the clean Parquet dataset."""
    if not path.exists():
        raise FileNotFoundError(f"Clean dataset not found: {path}")
    df = pd.read_parquet(path, engine="pyarrow")
    if "date" in df.columns and "Date" not in df.columns:
        df["Date"] = pd.to_datetime(df["date"])
    if "symbol" in df.columns and "Symbol" not in df.columns:
        df["Symbol"] = df["symbol"]
    if "expiry_date" in df.columns and "ExpiryDate" not in df.columns:
        df["ExpiryDate"] = pd.to_datetime(df["expiry_date"])
    if "close" in df.columns and "Close" not in df.columns:
        df["Close"] = df["close"]
    if "prev_close" in df.columns and "Previous Close" not in df.columns:
        df["Previous Close"] = df["prev_close"]
    if "volume_lots" in df.columns and "Volume" not in df.columns:
        df["Volume"] = df["volume_lots"]
    if "oi_lots" in df.columns and "OpenInterest" not in df.columns:
        df["OpenInterest"] = df["oi_lots"]
    if "no_trade" in df.columns and "ZeroVolume" not in df.columns:
        df["ZeroVolume"] = df["no_trade"]
    if "PriceOutlier" not in df.columns:
        df["PriceOutlier"] = False
    df["_data_source"] = "mcx"
    return df


def load_sample(sample_dir: Path = SAMPLE_DIR) -> pd.DataFrame:
    """Load bundled sample CSVs (offline fallback)."""
    csvs = sorted(sample_dir.glob("*.csv"))
    if not csvs:
        raise FileNotFoundError(f"No sample CSVs in {sample_dir}")
    frames = []
    for fp in csvs:
        df, _ = _clean_file(fp)
        if not df.empty:
            frames.append(df)
    if not frames:
        raise ValueError("Sample CSVs contained no valid gold rows")
    combined = pd.concat(frames, ignore_index=True)
    combined["Date"] = pd.to_datetime(combined["Date"])
    combined["ExpiryDate"] = pd.to_datetime(combined["ExpiryDate"])
    combined["_data_source"] = "sample"
    return combined.sort_values(["Symbol", "ExpiryDate", "Date"]).reset_index(drop=True)


def load_data() -> tuple[pd.DataFrame, str]:
    """
    Try to load clean Parquet; fall back to sample CSVs.
    Returns (dataframe, data_source) where data_source is "mcx" or "sample".
    Never mixes real and demo data.
    """
    try:
        df = load_clean()
        return df, "mcx"
    except FileNotFoundError:
        logger.info("No clean Parquet found; falling back to sample data.")
        df = load_sample()
        return df, "sample"

