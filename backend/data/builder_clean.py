"""
KARAT – Real MCX Bhavcopy ingestion and clean dataset builder.
Produces karat_clean.csv and quality_report.json from all valid available Bhavcopy files.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any
from collections import defaultdict, Counter

import pandas as pd

from backend.config import PROJECT_ROOT, CLEAN_DIR, RAW_DIR

logger = logging.getLogger(__name__)

BHAVCOPY_DIR = PROJECT_ROOT / "bhavcopy datasets"
OUTPUT_CSV = PROJECT_ROOT / "karat_clean.csv"
OUTPUT_PARQUET = CLEAN_DIR / "karat.parquet"
QUALITY_REPORT_PATH = CLEAN_DIR / "quality_report.json"
QUALITY_REPORT_ROOT_PATH = PROJECT_ROOT / "quality_report.json"

LOT_SIZES: dict[str, float] = {
    "GOLDM": 100.0,
    "GOLDTEN": 10.0,
    "GOLDGUINEA": 8.0,
    "GOLDPETAL": 1.0,
}

QUOTE_BASES: dict[str, float] = {
    "GOLDM": 10.0,
    "GOLDTEN": 10.0,
    "GOLDGUINEA": 8.0,
    "GOLDPETAL": 1.0,
}

PURITIES: dict[str, int] = {
    "GOLDM": 995,
    "GOLDTEN": 999,
    "GOLDGUINEA": 999,
    "GOLDPETAL": 999,
}

MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

# Known statutory market holidays for MCX Gold Futures
MCX_STATUTORY_HOLIDAYS = {
    "2026-10-02": "Mahatma Gandhi Jayanti (statutory national market holiday on MCX)"
}


def parse_expiry(s: Any) -> dt.date | None:
    if not s:
        return None
    s = str(s).strip().upper()
    import re
    m = re.match(r"^(\d{2})([A-Z]{3})(\d{4})$", s)
    if m:
        day = int(m.group(1))
        month = MONTH_MAP.get(m.group(2))
        year = int(m.group(3))
        if month:
            try:
                return dt.date(year, month, day)
            except ValueError:
                pass
    return None


def parse_row_date(s: Any) -> dt.date | None:
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None


def calculate_normalised_price(price: float, symbol: str) -> float:
    """Exact formula: price / quote_base * 999 / purity."""
    if price <= 0:
        return 0.0
    q_base = QUOTE_BASES[symbol]
    purity = PURITIES[symbol]
    return round((price / q_base) * (999.0 / purity), 2)


def build_karat_clean_csv(
    bhavcopy_dir: Path = BHAVCOPY_DIR,
    output_csv: Path = OUTPUT_CSV,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Builds karat_clean.csv and quality_report.json from all valid raw MCX Bhavcopy CSV files.
    Preserves contract identity using (symbol, expiry_date).
    Deterministic deduplication on (date, symbol, expiry_date).
    """
    files = sorted(bhavcopy_dir.glob("*.csv"))
    raw_rows: list[dict[str, Any]] = []

    files_discovered: list[str] = [f.name for f in files]
    files_used: list[str] = []
    files_rejected: list[dict[str, Any]] = []
    per_file_stats: dict[str, dict[str, Any]] = {}

    reasons_count: dict[str, int] = {
        "non_tracked_symbol": 0,
        "bad_format": 0,
    }

    total_raw_rows_scanned = 0

    for fp in files:
        fname = fp.name
        is_commodity_wise = "CommodiyWise" in fname or "CommodityWise" in fname
        file_raw_rows = 0
        file_tracked_rows = 0
        file_dates: set[str] = set()
        file_symbols: set[str] = set()

        try:
            with open(fp, encoding="utf-8-sig", errors="ignore") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    files_rejected.append({
                        "file": fname,
                        "reason": "empty_or_corrupt_csv"
                    })
                    continue

                for r in reader:
                    file_raw_rows += 1
                    total_raw_rows_scanned += 1
                    inst = r.get("Instrument Name", "").strip()
                    sym = r.get("Symbol", "").strip()

                    # In MCX Bhavcopy, commodity futures are instrument FUTCOM
                    # Commodity-wise files are dedicated FUTCOM records for gold contracts
                    if (inst != "FUTCOM" and not is_commodity_wise) or sym not in LOT_SIZES:
                        reasons_count["non_tracked_symbol"] += 1
                        continue

                    row_date = parse_row_date(r.get("Date", ""))
                    exp_date = parse_expiry(r.get("Expiry Date", ""))

                    if not row_date or not exp_date:
                        reasons_count["bad_format"] += 1
                        continue

                    try:
                        close = float(r.get("Close", 0) or 0)
                    except ValueError:
                        close = 0.0

                    try:
                        prev_close = float(r.get("Previous Close", 0) or 0)
                    except ValueError:
                        prev_close = 0.0

                    try:
                        vol_lots = int(float(r.get("Volume(Lots)", 0) or 0))
                    except ValueError:
                        vol_lots = 0

                    try:
                        oi_lots = int(float(r.get("Open Interest(Lots)", 0) or 0))
                    except ValueError:
                        oi_lots = 0

                    days_to_exp = (exp_date - row_date).days
                    lot_g = LOT_SIZES[sym]
                    grams_traded = vol_lots * lot_g
                    no_trade = (vol_lots == 0)

                    norm_close = calculate_normalised_price(close, sym)
                    norm_prev = calculate_normalised_price(prev_close, sym)

                    raw_rows.append({
                        "date": row_date.isoformat(),
                        "symbol": sym,
                        "expiry_date": exp_date.isoformat(),
                        "days_to_expiry": days_to_exp,
                        "close": close,
                        "prev_close": prev_close,
                        "norm_close": norm_close,
                        "norm_prev_close": norm_prev,
                        "volume_lots": vol_lots,
                        "grams_traded": grams_traded,
                        "oi_lots": oi_lots,
                        "no_trade": no_trade,
                        "source_file": fname,
                    })

                    file_tracked_rows += 1
                    file_dates.add(row_date.isoformat())
                    file_symbols.add(sym)

            if file_tracked_rows > 0:
                files_used.append(fname)
                sorted_f_dates = sorted(list(file_dates))
                per_file_stats[fname] = {
                    "total_rows_in_file": file_raw_rows,
                    "tracked_rows_extracted": file_tracked_rows,
                    "symbols": sorted(list(file_symbols)),
                    "distinct_dates": len(file_dates),
                    "date_min": sorted_f_dates[0],
                    "date_max": sorted_f_dates[-1],
                }
            else:
                files_rejected.append({
                    "file": fname,
                    "reason": "no_tracked_gold_rows_found"
                })

        except Exception as ex:
            files_rejected.append({
                "file": fname,
                "reason": f"file_read_error: {str(ex)}"
            })

    # Group records by (date, symbol, expiry_date) to detect conflicts and duplicates
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in raw_rows:
        key = (row["date"], row["symbol"], row["expiry_date"])
        grouped[key].append(row)

    total_tracked_observations = len(raw_rows)
    unique_keys_count = len(grouped)
    duplicate_rows_count = total_tracked_observations - unique_keys_count

    price_conflicts: list[dict[str, Any]] = []
    clean_rows: list[dict[str, Any]] = []

    for key, cand_rows in grouped.items():
        if len(cand_rows) == 1:
            clean_rows.append(cand_rows[0])
        else:
            # Check price conflict
            closes = set(r["close"] for r in cand_rows)
            if len(closes) > 1:
                # Log conflict
                conflict_entry = {
                    "key": {"date": key[0], "symbol": key[1], "expiry_date": key[2]},
                    "closes_observed": list(closes),
                    "sources": [r["source_file"] for r in cand_rows],
                    "resolution": "selected_row_with_higher_volume"
                }
                price_conflicts.append(conflict_entry)
                # Resolve deterministically: prefer traded row (highest volume)
                selected = max(cand_rows, key=lambda r: (r["volume_lots"], r["source_file"]))
            else:
                # All closes match: deterministic deduplication, keep the latest source file
                selected = sorted(cand_rows, key=lambda r: r["source_file"])[-1]

            clean_rows.append(selected)

    df = pd.DataFrame(clean_rows)
    if not df.empty:
        df = df.sort_values(["date", "symbol", "expiry_date"]).reset_index(drop=True)

    # Save CSVs
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(CLEAN_DIR / "karat_clean.csv", index=False)
    df.to_parquet(OUTPUT_PARQUET, index=False, engine="pyarrow")

    dates = sorted(df["date"].unique().tolist()) if not df.empty else []
    no_trade_count = int(df["no_trade"].sum()) if not df.empty else 0

    # Weekdays & Trading Calendar Verification
    missing_weekdays: list[str] = []
    known_holidays: dict[str, str] = {}
    unexplained_missing: list[str] = []

    if len(dates) >= 2:
        date_objs = [dt.date.fromisoformat(d) for d in dates]
        cur = date_objs[0]
        end = date_objs[-1]
        while cur <= end:
            if cur.weekday() < 5:  # Monday to Friday
                iso = cur.isoformat()
                if cur not in date_objs:
                    missing_weekdays.append(iso)
                    if iso in MCX_STATUTORY_HOLIDAYS:
                        known_holidays[iso] = MCX_STATUTORY_HOLIDAYS[iso]
                    else:
                        unexplained_missing.append(iso)
            cur += dt.timedelta(days=1)

    # Detailed row breakdown
    counts_by_contract = df["symbol"].value_counts().to_dict() if not df.empty else {}
    contract_expiry_counts = (
        df.groupby(["symbol", "expiry_date"]).size().to_dict()
        if not df.empty else {}
    )
    formatted_expiry_counts = {
        f"{sym} ({exp})": count for (sym, exp), count in contract_expiry_counts.items()
    }

    quality_report = {
        "status": "ready",
        "data_source": "mcx",
        "pipeline_version": "2.0_multi_file_historical",
        "total_files_scanned": len(files_discovered),
        "files_discovered": files_discovered,
        "files_used_count": len(files_used),
        "files_used": files_used,
        "files_rejected_count": len(files_rejected),
        "files_rejected": files_rejected,
        "per_file_breakdown": per_file_stats,
        "total_raw_rows_scanned": total_raw_rows_scanned,
        "tracked_gold_rows_extracted": total_tracked_observations,
        "duplicate_rows_removed": duplicate_rows_count,
        "valid_clean_rows_retained": len(df),
        "distinct_trading_dates_count": len(dates),
        "date_range": {
            "start": dates[0] if dates else None,
            "end": dates[-1] if dates else None,
        },
        "row_counts_by_contract": counts_by_contract,
        "row_counts_by_contract_and_expiry": formatted_expiry_counts,
        "no_trade_rows_count": no_trade_count,
        "trading_calendar_reconciliation": {
            "total_calendar_days": (dt.date.fromisoformat(dates[-1]) - dt.date.fromisoformat(dates[0])).days + 1 if len(dates) >= 2 else 0,
            "total_weekdays_mon_fri": len(dates) + len(missing_weekdays),
            "trading_days_present": len(dates),
            "missing_weekdays_count": len(missing_weekdays),
            "missing_weekdays": missing_weekdays,
            "statutory_market_holidays_confirmed": known_holidays,
            "unexplained_missing_trading_days": unexplained_missing,
        },
        "price_conflicts_detected": len(price_conflicts),
        "price_conflicts": price_conflicts,
        "rejections_by_reason": reasons_count,
    }

    # Save to clean dir and root
    with open(QUALITY_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(quality_report, f, indent=2)

    with open(QUALITY_REPORT_ROOT_PATH, "w", encoding="utf-8") as f:
        json.dump(quality_report, f, indent=2)

    return df, quality_report


if __name__ == "__main__":
    df, report = build_karat_clean_csv()
    print("=" * 60)
    print("KARAT MCX DATA REBUILD COMPLETE")
    print("=" * 60)
    print(f"Files processed: {report['files_used_count']} of {report['total_files_scanned']}")
    print(f"Clean rows: {report['valid_clean_rows_retained']}")
    print(f"Distinct trading dates: {report['distinct_trading_dates_count']}")
    print(f"Date range: {report['date_range']['start']} to {report['date_range']['end']}")
    print(f"Counts by contract: {report['row_counts_by_contract']}")
    print(f"Trading calendar: {report['trading_calendar_reconciliation']['trading_days_present']} trading days, {report['trading_calendar_reconciliation']['missing_weekdays_count']} holiday")
    print(f"Price conflicts: {report['price_conflicts_detected']}")
    print("=" * 60)
