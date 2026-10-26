"""
KARAT – data pipeline tests.

Covers:
- Expiry date parsing ("04SEP2026" format)
- DD/MM vs MM/DD date parsing
- Date-mismatch rejection
- Symbol stripping
- Sample CSV loading and quality report
- Data identity: keyed by (symbol, expiry_date), no continuous series
"""

from __future__ import annotations

import datetime as dt
import textwrap
from pathlib import Path
from io import StringIO

import pandas as pd
import pytest

from backend.data.parser import (
    parse_expiry_date,
    parse_response_date,
    load_sample,
    build_clean_dataset,
    _clean_file,
)
from backend.data.downloader import DateMismatchError
from backend.config import SAMPLE_DIR, TRACKED_SYMBOLS


# ──────────────────────────────────────────────────────────────────────
# Expiry date parsing
# ──────────────────────────────────────────────────────────────────────

class TestExpiryParsing:
    def test_standard_mcx_format(self):
        assert parse_expiry_date("04SEP2026") == dt.date(2026, 9, 4)

    def test_all_months(self):
        months = [
            ("15JAN2025", dt.date(2025, 1, 15)),
            ("28FEB2025", dt.date(2025, 2, 28)),
            ("05MAR2025", dt.date(2025, 3, 5)),
            ("30APR2025", dt.date(2025, 4, 30)),
            ("12MAY2025", dt.date(2025, 5, 12)),
            ("27JUN2025", dt.date(2025, 6, 27)),
            ("31JUL2025", dt.date(2025, 7, 31)),
            ("29AUG2025", dt.date(2025, 8, 29)),
            ("04SEP2025", dt.date(2025, 9, 4)),
            ("31OCT2025", dt.date(2025, 10, 31)),
            ("28NOV2025", dt.date(2025, 11, 28)),
            ("05DEC2025", dt.date(2025, 12, 5)),
        ]
        for s, expected in months:
            assert parse_expiry_date(s) == expected, f"Failed for {s}"

    def test_whitespace_stripped(self):
        assert parse_expiry_date("  04SEP2026  ") == dt.date(2026, 9, 4)

    def test_lowercase_accepted(self):
        # Our parser uppercases, so lowercase should work
        assert parse_expiry_date("04sep2026") == dt.date(2026, 9, 4)

    def test_iso_fallback(self):
        assert parse_expiry_date("2026-09-04") == dt.date(2026, 9, 4)

    def test_empty_returns_none(self):
        assert parse_expiry_date("") is None

    def test_garbage_returns_none(self):
        assert parse_expiry_date("NOTADATE") is None


# ──────────────────────────────────────────────────────────────────────
# Response date parsing (DD/MM vs MM/DD trap)
# ──────────────────────────────────────────────────────────────────────

class TestResponseDateParsing:
    def test_mm_dd_yyyy(self):
        """MCX responses use MM/DD/YYYY."""
        assert parse_response_date("01/15/2025") == dt.date(2025, 1, 15)

    def test_iso_format(self):
        assert parse_response_date("2025-01-15") == dt.date(2025, 1, 15)

    def test_whitespace_stripped(self):
        assert parse_response_date("  01/15/2025  ") == dt.date(2025, 1, 15)

    def test_empty_returns_none(self):
        assert parse_response_date("") is None

    def test_garbage_returns_none(self):
        assert parse_response_date("notadate") is None


# ──────────────────────────────────────────────────────────────────────
# Symbol stripping
# ──────────────────────────────────────────────────────────────────────

class TestSymbolStripping:
    def test_space_padded_symbol_cleaned(self, tmp_path):
        """Symbols with whitespace padding should be stripped."""
        csv_content = textwrap.dedent("""\
            Symbol,Date,ExpiryDate,Open,High,Low,Close,Volume,OpenInterest
            GOLDM   ,01/02/2025,05FEB2025,58500,58750,58400,58650,12500,35000
              GOLDTEN,01/02/2025,28FEB2025,59000,59200,58900,59100,3200,9500
        """)
        csv_path = tmp_path / "bhavcopy_2025-01-02.csv"
        csv_path.write_text(csv_content, encoding="utf-8")

        df, rejections = _clean_file(csv_path)
        assert len(df) == 2
        assert set(df["Symbol"].unique()) == {"GOLDM", "GOLDTEN"}
        # No whitespace in symbol names
        for sym in df["Symbol"]:
            assert sym == sym.strip()


# ──────────────────────────────────────────────────────────────────────
# Non-gold symbols are filtered out
# ──────────────────────────────────────────────────────────────────────

class TestSymbolFiltering:
    def test_non_gold_rejected(self, tmp_path):
        csv_content = textwrap.dedent("""\
            Symbol,Date,ExpiryDate,Open,High,Low,Close,Volume,OpenInterest
            GOLDM,01/02/2025,05FEB2025,58500,58750,58400,58650,12500,35000
            SILVER,01/02/2025,05FEB2025,72000,72500,71500,72200,5000,12000
            CRUDEOIL,01/02/2025,19FEB2025,6200,6300,6150,6250,8000,20000
        """)
        csv_path = tmp_path / "bhavcopy_2025-01-02.csv"
        csv_path.write_text(csv_content, encoding="utf-8")

        df, rejections = _clean_file(csv_path)
        assert len(df) == 1
        assert df.iloc[0]["Symbol"] == "GOLDM"
        # Should have a rejection for non-gold symbols
        rej_reasons = [r["reason"] for r in rejections]
        assert "non_gold_symbol" in rej_reasons


# ──────────────────────────────────────────────────────────────────────
# Data identity: keyed by (symbol, expiry_date)
# ──────────────────────────────────────────────────────────────────────

class TestDataIdentity:
    def test_multiple_expiries_per_symbol_preserved(self):
        """
        A single symbol (GOLDM) should have multiple rows per date,
        one for each expiry. We NEVER collapse to a near-month series.
        """
        df = load_sample(SAMPLE_DIR)
        # Pick a date where we know GOLDM has multiple expiries
        date_mask = df["Date"] == pd.Timestamp("2025-01-02")
        goldm = df.loc[date_mask & (df["Symbol"] == "GOLDM")]
        # Should have multiple rows — one per expiry
        assert len(goldm) >= 2, (
            "Expected multiple GOLDM rows (one per expiry), got "
            f"{len(goldm)}. Identity rule: key by (symbol, expiry_date)."
        )
        # Each row should have a different ExpiryDate
        assert goldm["ExpiryDate"].nunique() == len(goldm)


# ──────────────────────────────────────────────────────────────────────
# Sample data loading
# ──────────────────────────────────────────────────────────────────────

class TestSampleLoading:
    def test_loads_all_symbols(self):
        df = load_sample(SAMPLE_DIR)
        loaded_symbols = set(df["Symbol"].unique())
        expected = set(TRACKED_SYMBOLS)
        assert loaded_symbols == expected, (
            f"Expected {expected}, got {loaded_symbols}"
        )

    def test_dates_are_datetime(self):
        df = load_sample(SAMPLE_DIR)
        assert pd.api.types.is_datetime64_any_dtype(df["Date"])
        assert pd.api.types.is_datetime64_any_dtype(df["ExpiryDate"])

    def test_numerics_are_numeric(self):
        df = load_sample(SAMPLE_DIR)
        for col in ["Open", "High", "Low", "Close", "Volume", "OpenInterest"]:
            assert pd.api.types.is_numeric_dtype(df[col]), (
                f"Column {col} should be numeric"
            )

    def test_no_duplicates(self):
        df = load_sample(SAMPLE_DIR)
        key_cols = ["Symbol", "ExpiryDate", "Date"]
        dupes = df.duplicated(subset=key_cols)
        assert not dupes.any(), f"Found {dupes.sum()} duplicate rows"

    def test_sorted_by_key(self):
        df = load_sample(SAMPLE_DIR)
        # Should be sorted by Symbol, ExpiryDate, Date
        sorted_df = df.sort_values(["Symbol", "ExpiryDate", "Date"])
        pd.testing.assert_frame_equal(df.reset_index(drop=True),
                                       sorted_df.reset_index(drop=True))


# ──────────────────────────────────────────────────────────────────────
# Quality report
# ──────────────────────────────────────────────────────────────────────

class TestQualityReport:
    def test_build_clean_from_sample(self, tmp_path):
        """Build a clean Parquet from sample CSVs and verify the report."""
        import shutil
        # Copy sample files to tmp raw dir
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        for f in SAMPLE_DIR.glob("*.csv"):
            shutil.copy(f, raw_dir / f"bhavcopy_{f.stem}.csv")

        out_path = tmp_path / "clean" / "test.parquet"
        report = build_clean_dataset(raw_dir=raw_dir, output_path=out_path)

        assert report["status"] == "ok"
        assert report["total_rows"] > 0
        assert out_path.exists()

        # Reload and verify
        df = pd.read_parquet(out_path)
        assert len(df) == report["total_rows"]


# ──────────────────────────────────────────────────────────────────────
# Zero-volume flagging
# ──────────────────────────────────────────────────────────────────────

class TestZeroVolume:
    def test_zero_volume_flagged(self, tmp_path):
        csv_content = textwrap.dedent("""\
            Symbol,Date,ExpiryDate,Open,High,Low,Close,Volume,OpenInterest
            GOLDM,01/02/2025,05FEB2025,58500,58750,58400,58650,0,35000
            GOLDM,01/02/2025,05MAR2025,58800,59000,58700,58900,8500,28000
        """)
        csv_path = tmp_path / "bhavcopy_2025-01-02.csv"
        csv_path.write_text(csv_content, encoding="utf-8")

        df, _ = _clean_file(csv_path)
        assert df.iloc[0]["ZeroVolume"] == True
        assert df.iloc[1]["ZeroVolume"] == False


# ──────────────────────────────────────────────────────────────────────
# Date mismatch error class and behavior
# ──────────────────────────────────────────────────────────────────────

class TestDateMismatch:
    def test_error_class_exists(self):
        with pytest.raises(DateMismatchError):
            raise DateMismatchError("requested 2025-01-02, got 2025-01-03")

    def test_message(self):
        err = DateMismatchError("test message")
        assert "test message" in str(err)

    def test_fetch_one_day_raises_on_date_mismatch(self, monkeypatch):
        """When MCX returns a different date (e.g. latest holiday fallback), raise DateMismatchError."""
        from backend.data.downloader import _fetch_one_day

        class MockResponse:
            def raise_for_status(self):
                pass
            def json(self):
                # Request date was 2025-01-02, but response has 01/01/2025 (MM/DD/YYYY)
                return [
                    {
                        "Symbol": "GOLDM",
                        "Date": "01/01/2025",
                        "ExpiryDate": "05FEB2025",
                        "Open": "58000",
                        "High": "58500",
                        "Low": "57900",
                        "Close": "58200",
                        "Volume": "1000",
                        "OpenInterest": "5000",
                    }
                ]

        import requests
        monkeypatch.setattr(requests, "post", lambda *args, **kwargs: MockResponse())

        with pytest.raises(DateMismatchError) as exc_info:
            _fetch_one_day(dt.date(2025, 1, 2), rate_limit=0)
        assert "requested 2025-01-02, got 2025-01-01" in str(exc_info.value)


# ──────────────────────────────────────────────────────────────────────
# Data Source and Outlier Retention Tests
# ──────────────────────────────────────────────────────────────────────

class TestDataSourceAndOutliers:
    def test_load_data_source_label(self):
        from backend.data.parser import load_data
        df, source = load_data()
        assert source in ("mcx", "sample")
        assert not df.empty

    def test_price_outliers_not_silently_dropped(self, tmp_path):
        """Outliers should have PriceOutlier=True but still be preserved in the dataset."""
        csv_content = textwrap.dedent("""\
            Symbol,Date,ExpiryDate,Open,High,Low,Close,Volume,OpenInterest
            GOLDM,01/02/2025,05FEB2025,58500,58750,58400,58650,12500,35000
            GOLDM,01/02/2025,05MAR2025,58800,59000,58700,58900,8500,28000
            GOLDM,01/02/2025,05APR2025,59100,59300,59000,59200,4200,15000
            GOLDM,01/02/2025,05MAY2025,999999,999999,999999,999999,10,100
        """)
        csv_path = tmp_path / "bhavcopy_2025-01-02.csv"
        csv_path.write_text(csv_content, encoding="utf-8")

        df, rejections = _clean_file(csv_path)
        # All 4 rows retained
        assert len(df) == 4
        # Outlier is flagged
        assert df["PriceOutlier"].sum() >= 1
        # Rejection/flag log contains price_outlier_flagged
        reasons = [r["reason"] for r in rejections]
        assert "price_outlier_flagged" in reasons


# ──────────────────────────────────────────────────────────────────────
# Step 1: Data Status & Quality Audit Suite
# ──────────────────────────────────────────────────────────────────────

class TestDataStatusAndQuality:
    def test_sample_data_status_is_demo(self):
        from backend.data.parser import get_data_status, load_sample
        df = load_sample()
        status, last_date = get_data_status(df, "sample")
        assert status == "demo"
        assert last_date is not None
        assert len(last_date) == 10  # YYYY-MM-DD

    def test_empty_dataframe_status_is_incomplete(self):
        from backend.data.parser import get_data_status
        empty_df = pd.DataFrame()
        status, last_date = get_data_status(empty_df, "mcx")
        assert status == "incomplete"
        assert last_date is None

    def test_missing_contracts_marked_incomplete(self):
        from backend.data.parser import get_data_status
        # DataFrame with only GOLDM and missing other contracts
        mock_df = pd.DataFrame({
            "Symbol": ["GOLDM"],
            "Date": [pd.Timestamp("2026-06-01")],
            "ExpiryDate": [pd.Timestamp("2026-08-05")],
            "Close": [70000.0],
        })
        status, _ = get_data_status(mock_df, "mcx", date="2026-06-01")
        assert status == "incomplete"

    def test_complete_mcx_marked_real(self):
        from backend.data.parser import get_data_status
        # All required contracts present on same date
        mock_df = pd.DataFrame({
            "Symbol": ["GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"],
            "Date": [pd.Timestamp("2026-06-01")] * 4,
            "ExpiryDate": [pd.Timestamp("2026-08-05")] * 4,
            "Close": [70000.0, 7000.0, 56000.0, 7000.0],
        })
        status, last_date = get_data_status(mock_df, "mcx", date="2026-06-01")
        assert status == "real"
        assert last_date == "2026-06-01"

    def test_goldten_before_april_2025_not_required_for_completeness(self):
        from backend.data.parser import get_data_status
        # In Jan 2025, GOLDTEN was not listed yet; GOLDM, GOLDGUINEA, GOLDPETAL suffice
        mock_df = pd.DataFrame({
            "Symbol": ["GOLDM", "GOLDGUINEA", "GOLDPETAL"],
            "Date": [pd.Timestamp("2025-01-15")] * 3,
            "ExpiryDate": [pd.Timestamp("2025-02-05")] * 3,
            "Close": [60000.0, 48000.0, 6000.0],
        })
        status, last_date = get_data_status(mock_df, "mcx", date="2025-01-15")
        assert status == "real"
        assert last_date == "2025-01-15"

    def test_missing_trading_days_gap_marks_incomplete(self):
        from backend.data.parser import get_data_status
        # 10 calendar days gap between sessions
        mock_df = pd.DataFrame({
            "Symbol": ["GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"] * 2,
            "Date": [pd.Timestamp("2026-06-01")] * 4 + [pd.Timestamp("2026-06-11")] * 4,
            "ExpiryDate": [pd.Timestamp("2026-08-05")] * 8,
            "Close": [70000.0] * 8,
        })
        status, _ = get_data_status(mock_df, "mcx")
        assert status == "incomplete"

    def test_purity_validation_mixed_rows(self):
        from backend.data.parser import validate_dataset_purity
        mixed_df = pd.DataFrame({
            "Symbol": ["GOLDM", "GOLDM"],
            "_data_source": ["mcx", "sample"],
        })
        assert not validate_dataset_purity(mixed_df, "mcx")
        assert not validate_dataset_purity(mixed_df, "sample")

    def test_date_mismatch_rejection_in_clean_file(self, tmp_path):
        from backend.data.parser import _clean_file
        # File named for 2025-01-05 but rows say 01/02/2025
        csv_content = textwrap.dedent("""\
            Symbol,Date,ExpiryDate,Open,High,Low,Close,Volume,OpenInterest
            GOLDM,01/02/2025,05FEB2025,58500,58750,58400,58650,12500,35000
        """)
        csv_path = tmp_path / "bhavcopy_2025-01-05.csv"
        csv_path.write_text(csv_content, encoding="utf-8")

        df, rejections = _clean_file(csv_path)
        assert len(df) == 0  # mismatched row rejected
        reasons = [r["reason"] for r in rejections]
        assert "date_mismatch" in reasons

    def test_quality_audit_report_structure(self):
        from backend.data.parser import get_data_quality_report, load_data
        df, source = load_data()
        report = get_data_quality_report(df, source)
        assert report["data_status"] in ("real", "demo", "incomplete")
        assert report["data_source"] == source
        assert report["last_verified_trading_date"] is not None
        assert "total_rows_loaded" in report
        assert "rejections" in report
        assert "rejections_by_reason" in report
        assert "missing_trading_days" in report
        assert "zero_volume_rows" in report
        assert "price_outliers_flagged" in report
        assert report["raw_files_cached_untouched"] is True

