"""
KARAT – CLI entry point for the data pipeline.

Usage:
    python -m backend.data.cli download --start 2025-01-01 --end 2025-03-31
    python -m backend.data.cli build
    python -m backend.data.cli report
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys

from backend.config import RAW_DIR, PARQUET_PATH, SAMPLE_DIR
from backend.data.downloader import download_range
from backend.data.parser import build_clean_dataset, load_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def cmd_download(args: argparse.Namespace) -> None:
    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    print(f"Downloading MCX Bhavcopy: {start} → {end}")
    summary = download_range(start, end)
    print(json.dumps(summary, indent=2, default=str))


def cmd_build(args: argparse.Namespace) -> None:
    print(f"Building clean dataset from raw files in {RAW_DIR}")
    report = build_clean_dataset()
    print(json.dumps(report, indent=2, default=str))


def cmd_report(args: argparse.Namespace) -> None:
    df, source = load_data()
    print(f"Data source: {source}")
    print(f"Rows: {len(df)}")
    print(f"Symbols: {sorted(df['Symbol'].unique().tolist())}")
    print(f"Date range: {df['Date'].min()} → {df['Date'].max()}")
    print(f"Trading days: {df['Date'].nunique()}")
    for sym in sorted(df["Symbol"].unique()):
        sub = df[df["Symbol"] == sym]
        print(f"  {sym}: {len(sub)} rows, "
              f"{sub['ExpiryDate'].nunique()} expiries, "
              f"dates {sub['Date'].min().date()} → {sub['Date'].max().date()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="KARAT data pipeline")
    sub = parser.add_subparsers(dest="command")

    dl = sub.add_parser("download", help="Download MCX Bhavcopy")
    dl.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    dl.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")

    sub.add_parser("build", help="Build clean Parquet from raw CSVs")
    sub.add_parser("report", help="Show data summary")

    args = parser.parse_args()
    if args.command == "download":
        cmd_download(args)
    elif args.command == "build":
        cmd_build(args)
    elif args.command == "report":
        cmd_report(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
