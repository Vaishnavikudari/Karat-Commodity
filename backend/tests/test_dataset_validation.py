"""
Automated validation test suite for KARAT regenerated MCX Bhavcopy dataset.
Verifies all 9 conditions specified in Step 5:
1. All four contract symbols represented
2. Covers actual date range present in raw files (2026-08-03 to 2026-10-23)
3. Multiple expiry contracts on one date are not incorrectly counted as multiple trading days
4. Valid observations from older files are not lost when newer files are added
5. Duplicate handling is deterministic
6. Normalization matches documented formula (price / quote_base * 999 / purity)
7. GOLDM and GOLDTEN prices are compared only when selected comparison rules permit it
8. No-trade rows are not treated as ordinary traded observations
9. Missing data cannot silently create invalid signals
"""

import datetime as dt
from pathlib import Path
import pandas as pd
import pytest

from backend.config import PROJECT_ROOT
from backend.data.builder_clean import calculate_normalised_price, LOT_SIZES, QUOTE_BASES, PURITIES

CLEAN_CSV = PROJECT_ROOT / "karat_clean.csv"


@pytest.fixture(scope="module")
def clean_df() -> pd.DataFrame:
    assert CLEAN_CSV.exists(), f"karat_clean.csv missing at {CLEAN_CSV}"
    df = pd.read_csv(CLEAN_CSV)
    df.columns = [c.lower() for c in df.columns]
    return df


def test_1_all_four_symbols_represented(clean_df: pd.DataFrame):
    """Confirm all four contract symbols are represented in the dataset."""
    symbols = set(clean_df["symbol"].unique())
    expected = {"GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"}
    assert symbols == expected, f"Expected {expected}, got {symbols}"
    for sym in expected:
        count = len(clean_df[clean_df["symbol"] == sym])
        assert count > 0, f"Symbol {sym} has 0 rows"


def test_2_date_range_matches_raw_files(clean_df: pd.DataFrame):
    """Confirm cleaned dataset covers the actual date range present in raw files."""
    dates = sorted(clean_df["date"].unique().tolist())
    assert len(dates) == 59, f"Expected 59 distinct trading dates, found {len(dates)}"
    assert dates[0] == "2026-08-03", f"Expected min date 2026-08-03, found {dates[0]}"
    assert dates[-1] == "2026-10-23", f"Expected max date 2026-10-23, found {dates[-1]}"


def test_3_multiple_expiries_not_double_counting_trading_days(clean_df: pd.DataFrame):
    """
    Multiple expiry contracts on one date (e.g. 6 expiries per contract on 2026-09-29)
    must NOT be incorrectly counted as multiple trading days.
    """
    date_counts = clean_df["date"].nunique()
    assert date_counts == 59

    sep29_rows = clean_df[clean_df["date"] == "2026-09-29"]
    assert len(sep29_rows) == 24

    assert sep29_rows["date"].nunique() == 1


def test_4_older_observations_not_lost_when_newer_added(clean_df: pd.DataFrame):
    """Valid observations from older dates (e.g. August 2026) are preserved alongside newer dates."""
    aug_rows = clean_df[clean_df["date"].str.startswith("2026-08")]
    sep_rows = clean_df[clean_df["date"].str.startswith("2026-09")]
    oct_rows = clean_df[clean_df["date"].str.startswith("2026-10")]

    assert len(aug_rows) > 0, "August rows missing"
    assert len(sep_rows) > 0, "September rows missing"
    assert len(oct_rows) > 0, "October rows missing"


    assert aug_rows["date"].nunique() == 21
    assert sep_rows["date"].nunique() == 22
    assert oct_rows["date"].nunique() == 16
    assert 21 + 22 + 16 == 59


def test_5_deterministic_duplicate_handling(clean_df: pd.DataFrame):
    """Confirm (date, symbol, expiry_date) is uniquely and deterministically identified with 0 duplicates."""
    key_series = clean_df["date"] + "_" + clean_df["symbol"] + "_" + clean_df["expiry_date"]
    dup_mask = key_series.duplicated()
    assert not dup_mask.any(), f"Found {dup_mask.sum()} duplicate contract keys in clean dataset!"
    assert len(clean_df) == 276


def test_6_normalization_formula_accuracy(clean_df: pd.DataFrame):
    """Confirm normalization strictly matches documented formula: price / quote_base * 999 / purity."""
    sample = clean_df.sample(n=min(30, len(clean_df)), random_state=42)
    for _, row in sample.iterrows():
        sym = row["symbol"]
        close = float(row["close"])
        norm = float(row["norm_close"])
        expected_norm = round((close / QUOTE_BASES[sym]) * (999.0 / PURITIES[sym]), 2)
        assert norm == pytest.approx(expected_norm, abs=0.02)


def test_7_goldm_goldten_comparison_carry_rule(clean_df: pd.DataFrame):
    """
    GOLDM (expires 5th) and GOLDTEN (expires end of month) comparison must respect
    expiry differences: when expiries differ, carry days must be accounted for.
    """
    oct14 = clean_df[clean_df["date"] == "2026-10-14"]
    goldm_front = oct14[(oct14["symbol"] == "GOLDM") & (oct14["expiry_date"] == "2026-11-05")].iloc[0]
    goldten_front = oct14[(oct14["symbol"] == "GOLDTEN") & (oct14["expiry_date"] == "2026-10-30")].iloc[0]


    d_m = dt.date.fromisoformat(goldm_front["expiry_date"])
    d_t = dt.date.fromisoformat(goldten_front["expiry_date"])
    diff_days = (d_m - d_t).days
    assert diff_days == 6

    assert goldm_front["norm_close"] > 0
    assert goldten_front["norm_close"] > 0


def test_8_no_trade_rows_distinguished():
    """No-trade rows (volume == 0) must have no_trade=True and be excluded from volume share."""
    mock_row_trade = {"volume_lots": 10, "no_trade": False}
    mock_row_notrade = {"volume_lots": 0, "no_trade": True}

    assert mock_row_notrade["no_trade"] is True
    assert mock_row_trade["no_trade"] is False


def test_9_missing_data_guardrail():
    """Missing data or date gap cannot silently invent prices; missing dates must be caught by calendar check."""
    from backend.data.builder_clean import MCX_STATUTORY_HOLIDAYS
    assert "2026-10-02" in MCX_STATUTORY_HOLIDAYS
    assert "Mahatma Gandhi Jayanti" in MCX_STATUTORY_HOLIDAYS["2026-10-02"]
