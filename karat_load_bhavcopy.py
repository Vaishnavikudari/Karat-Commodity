"""
KARAT — MCX Bhavcopy Ingestion & Cleaning Entry Point
Rebuilds karat_clean.csv and quality_report.json from all valid Bhavcopy CSV files.
"""

import sys
from pathlib import Path


root = Path(__file__).resolve().parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from backend.data.builder_clean import build_karat_clean_csv

if __name__ == "__main__":
    df, report = build_karat_clean_csv()
    print("=" * 60)
    print("KARAT MCX DATA REBUILD COMPLETE")
    print("=" * 60)
    print(f"Files processed: {report['files_used_count']} of {report['total_files_scanned']}")
    print(f"Clean rows: {report['valid_clean_rows_retained']}")
    print(f"Distinct trading dates: {report['distinct_trading_dates_count']}")
    print(f"Date range: {report['date_range']['start']} to {report['date_range']['end']}")
    print(f"Row counts by contract: {report['row_counts_by_contract']}")
    print(f"Trading calendar: {report['trading_calendar_reconciliation']['trading_days_present']} trading days, {report['trading_calendar_reconciliation']['missing_weekdays_count']} holiday")
    print(f"Price conflicts: {report['price_conflicts_detected']}")
    print("=" * 60)
