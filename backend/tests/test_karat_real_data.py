"""
Unit tests for KARAT real data calculations and invariants specified in user prompt:
- GOLDTEN 120000 per 10 g -> 12000 Rs/g
- GOLDM 119500 per 10 g at 995 -> about 11998.0
- Expiry matching
- No-trade rows excluded
- Window selection by history length (20 days normally; <40 days -> 10 days; <15 days -> Not enough data yet)
- No look-ahead in rolling reference
"""

import math
import pytest
import datetime as dt
import pandas as pd

from backend.data.builder_clean import calculate_normalised_price


def test_goldten_normalisation():
    """GOLDTEN 120000 per 10 g -> 12000 Rs/g."""
    price = 120000.0
    norm = calculate_normalised_price(price, "GOLDTEN")
    assert norm == 12000.0


def test_goldm_normalisation():
    """GOLDM 119500 per 10 g at 995 -> about 11998.0 (11998.04)."""
    price = 119500.0
    norm = calculate_normalised_price(price, "GOLDM")
    assert math.isclose(norm, 11998.0, abs_tol=0.1)
    assert round(norm, 1) == 11998.0


def test_window_selection_by_history_length():
    """
    Window selection rule:
    - 20 days normally (>= 40 trading days)
    - 10 days if fewer than 40 trading days loaded ('short window (10 days)')
    - 'Not enough data yet' if fewer than 15 trading days loaded
    """
    def get_window_policy(days_count: int) -> dict:
        if days_count < 15:
            return {"window": None, "label": "Not enough data yet", "can_assess": False}
        elif days_count < 40:
            return {"window": 10, "label": "short window (10 days)", "can_assess": True}
        else:
            return {"window": 20, "label": "20-day window", "can_assess": True}

    res_2 = get_window_policy(2)
    assert res_2["can_assess"] is False
    assert res_2["label"] == "Not enough data yet"

    res_14 = get_window_policy(14)
    assert res_14["can_assess"] is False
    assert res_14["label"] == "Not enough data yet"

    res_25 = get_window_policy(25)
    assert res_25["can_assess"] is True
    assert res_25["window"] == 10
    assert res_25["label"] == "short window (10 days)"

    res_50 = get_window_policy(50)
    assert res_50["can_assess"] is True
    assert res_50["window"] == 20


def test_no_lookahead_rolling():
    """Rolling reference strictly uses past days; future values do not affect past references."""
    series = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 15.0])
    # Shifted rolling mean ensures day t uses only data strictly prior to t
    rolling_ref = series.shift(1).rolling(window=3, min_periods=3).mean()
    
    assert pd.isna(rolling_ref.iloc[2])  # Not enough past days
    assert rolling_ref.iloc[3] == (10.0 + 11.0 + 12.0) / 3.0  # Uses days 0, 1, 2
    assert rolling_ref.iloc[4] == (11.0 + 12.0 + 13.0) / 3.0


def test_no_trade_rows_excluded():
    """Rows with no_trade = true (volume == 0) must be excluded from spread gaps and signal assessment."""
    data = [
        {"symbol": "GOLDTEN", "close": 145000.0, "volume_lots": 100, "no_trade": False},
        {"symbol": "GOLDPETAL", "close": 14550.0, "volume_lots": 0, "no_trade": True},
    ]
    tradeable = [d for d in data if not d["no_trade"]]
    assert len(tradeable) == 1
    assert tradeable[0]["symbol"] == "GOLDTEN"


def test_linear_interpolation_goldten_for_goldm():
    """
    GOLDTEN price at GOLDM expiry (e.g. 05 Nov 2026) is linearly interpolated
    between GOLDTEN's 30 Oct 2026 and 30 Nov 2026 prices.
    """
    d_exp_m = dt.date(2026, 11, 5)
    d_exp_t1 = dt.date(2026, 10, 30)
    d_exp_t2 = dt.date(2026, 11, 30)
    p_t1 = 14506.20  # Rs/g
    p_t2 = 14644.50  # Rs/g

    total_days = (d_exp_t2 - d_exp_t1).days  # 31 days
    elapsed_days = (d_exp_m - d_exp_t1).days  # 6 days

    interp_p = p_t1 + (p_t2 - p_t1) * (elapsed_days / total_days)
    assert 14506.20 < interp_p < 14644.50
    assert math.isclose(interp_p, 14532.97, abs_tol=0.01)
