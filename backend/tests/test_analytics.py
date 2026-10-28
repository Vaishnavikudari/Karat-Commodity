"""
KARAT – Module 2 Analytics Tests.

Covers:
1. Normaliser worked check from official specification:
   - GOLDTEN: ₹120,000 per 10 g (999) = ₹12,000.0/g
   - GOLDM: ₹119,500 per 10 g (995) = ₹11,997.99/g (~₹11,998.0/g)
   - Gap: ~1.68 bps (~1.7 bps)
2. Pair spread: spread_bps(a, b) = (norm_a - norm_b) / norm_b * 10000 across all 4-contract pairs.
3. No look-ahead: altering future data does NOT change z-score at day t.
4. Liquidity scoring and thin contract flagging proxy.
5. Term structure curves and carry-adjusted spreads.
6. Signal rule: qualifying entry vs 'none' on non-qualifying days.
"""

from __future__ import annotations

import datetime as dt
import numpy as np
import pandas as pd
import pytest

from backend.config import CONTRACTS
from backend.data.parser import load_sample
from backend.analytics.normaliser import (
    normalise_price,
    normalise_dataframe,
    get_normalised_snapshot,
)
from backend.analytics.spread import (
    compute_spread_series,
    estimate_round_trip_cost,
    get_spread_summary,
)
from backend.analytics.term_structure import get_term_structure
from backend.analytics.signals import evaluate_pair_signal, get_all_active_signals


class TestNormaliserWorkedCheck:
    def test_official_worked_example(self):
        """
        Worked check from specification:
        GOLDTEN 120000 per 10 g = 12000 Rs/g
        GOLDM 119500 per 10 g at 995 = about 11998.0 Rs/g
        gap about 1.7 bps
        """
        goldten_spec = CONTRACTS["GOLDTEN"]
        goldm_spec = CONTRACTS["GOLDM"]

        norm_goldten = normalise_price(120000.0, goldten_spec)
        norm_goldm = normalise_price(119500.0, goldm_spec)

        assert norm_goldten == pytest.approx(12000.0, rel=1e-5)
        assert norm_goldm == pytest.approx(11997.9899, rel=1e-4)
        assert round(norm_goldm, 1) == 11998.0


        gap_bps = (norm_goldten - norm_goldm) / norm_goldm * 10000.0
        assert round(gap_bps, 1) == 1.7 or abs(gap_bps - 1.675) < 0.05

    def test_guinea_and_petal_normalisation(self):
        """Verify 8g and 1g contracts at 999 purity."""
        guinea_spec = CONTRACTS["GOLDGUINEA"]
        petal_spec = CONTRACTS["GOLDPETAL"]


        assert normalise_price(48000.0, guinea_spec) == pytest.approx(6000.0, rel=1e-5)

        assert normalise_price(6000.0, petal_spec) == pytest.approx(6000.0, rel=1e-5)


class TestPairSpreadAllCombinations:
    def test_all_contract_pairs_supported(self):
        """Verify spread calculation works across all 6 combinations of the 4 contracts."""
        df = load_sample()
        pairs = [
            ("GOLDM", "GOLDTEN"),
            ("GOLDM", "GOLDGUINEA"),
            ("GOLDM", "GOLDPETAL"),
            ("GOLDTEN", "GOLDGUINEA"),
            ("GOLDTEN", "GOLDPETAL"),
            ("GOLDGUINEA", "GOLDPETAL"),
        ]

        for a, b in pairs:
            spread_df = compute_spread_series(df, symbol_a=a, symbol_b=b, window=5)
            assert not spread_df.empty, f"Spread series for pair {a}/{b} was empty"
            assert "spread_bps" in spread_df.columns
            assert "z_score" in spread_df.columns
            assert "carry_adjusted_spread_bps" in spread_df.columns


class TestNoLookAhead:
    def test_future_data_does_not_affect_past_z_score(self):
        """
        CRITICAL QUANT TEST:
        Altering data on days > t must NOT change the rolling z-score at day t.
        """
        df = load_sample()
        window = 10


        base_spread = compute_spread_series(df, "GOLDM", "GOLDTEN", window=window)
        assert len(base_spread) >= 15


        t_idx = 10
        target_date = base_spread.iloc[t_idx]["date"]
        baseline_z_at_t = base_spread.iloc[t_idx]["z_score"]


        perturbed_df = df.copy()
        future_mask = perturbed_df["Date"] > target_date
        perturbed_df.loc[future_mask, "Close"] = perturbed_df.loc[future_mask, "Close"] * 5.0
        perturbed_df.loc[future_mask, "Volume"] = 9999999


        new_spread = compute_spread_series(perturbed_df, "GOLDM", "GOLDTEN", window=window)
        new_z_at_t = new_spread.loc[new_spread["date"] == target_date, "z_score"].iloc[0]


        assert baseline_z_at_t == pytest.approx(new_z_at_t, rel=1e-6), (
            f"Look-ahead bias detected! z-score at {target_date} changed from "
            f"{baseline_z_at_t} to {new_z_at_t} when future prices were altered."
        )


class TestLiquidityProxy:
    def test_thin_contract_flagging(self):
        """Contracts with volume < 50 or OI < 100 are flagged as thin."""
        df = load_sample()
        snapshot = get_normalised_snapshot(df)
        assert len(snapshot) > 0

        for item in snapshot:
            vol = item.get("volume")
            oi = item.get("open_interest")
            status = item.get("liquidity_status")
            if vol is not None and oi is not None:
                if vol < 50 or oi < 100:
                    assert status in ("thin", "unavailable")
                else:
                    assert status == "liquid"


class TestTermStructureAndCarry:
    def test_term_structure_generation(self):
        df = load_sample()
        ts = get_term_structure(df)
        assert "curves" in ts
        assert len(ts["curves"]) > 0
        assert "disclaimer" in ts

        for curve in ts["curves"]:
            assert "symbol" in curve
            assert "points" in curve
            if curve["points"]:
                for pt in curve["points"]:
                    assert "days_to_expiry" in pt
                    assert "normalised_price" in pt
                    assert "annualized_carry_pct" in pt


class TestSignalRules:
    def test_signals_quiet_or_explicit(self):
        df = load_sample()
        sig = evaluate_pair_signal(df, "GOLDM", "GOLDTEN", window=5)

        assert "has_signal" in sig
        assert "signal_state" in sig
        if not sig["has_signal"]:
            assert sig["signal_state"] == "none"
            assert sig["action"] == "none"
        else:
            assert sig["signal_state"] == "entry"
            assert sig["action"] != "none"
            assert abs(sig["z_score"]) >= 2.0
            assert sig["expected_net_edge_bps"] > 0
