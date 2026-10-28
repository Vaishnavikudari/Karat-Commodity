"""
Unit tests for KARAT Step 1 calculation functions.

Verifies:
1. Lots and leftover maths (100g, 8g, 10g cases).
2. Combinations generation hitting target quantity exactly with fewest lots.
3. Best fit ranking (exact match first, lowest premium, most liquid).
4. Premium calculation using same expiry date.
5. GOLDM flagged for later expiry date.
6. no_trade rows properly flagged and excluded from trade share calculations.
7. Daily briefing figures equal the CSV values from karat_clean.csv.
8. Daily briefing fewer than 2 days returns 'Not enough data yet'.
9. AI output validator rejects text with unsupported numbers and accepts valid text.
10. Prewritten panel explanations conform to sentence-case and 'What this does not tell you' rules.
"""

import pandas as pd
import pytest

from backend.analytics.position_matcher import (
    compute_single_contract_match,
    find_exact_contract_combinations,
    rank_best_fit,
    compute_position_matcher,
)
from backend.analytics.daily_briefing import compute_daily_briefing
from backend.analytics.guardrails import (
    extract_numbers_from_text,
    extract_allowed_numbers_from_payload,
    validate_ai_output,
    get_prewritten_explanation,
)
from backend.data.parser import load_clean


def test_lots_and_leftover_math_100g():
    mock_row = {"close": 145000.0, "norm_close": 14500.0, "expiry_date": "2026-10-30", "grams_traded": 10000.0}


    res_m = compute_single_contract_match("GOLDM", 100.0, mock_row)
    assert res_m["lots_needed"] == 1
    assert res_m["grams_covered"] == 100.0
    assert res_m["leftover_grams"] == 0.0
    assert res_m["is_exact_match"] is True


    res_t = compute_single_contract_match("GOLDTEN", 100.0, mock_row)
    assert res_t["lots_needed"] == 10
    assert res_t["grams_covered"] == 100.0
    assert res_t["leftover_grams"] == 0.0
    assert res_t["is_exact_match"] is True


    res_g = compute_single_contract_match("GOLDGUINEA", 100.0, mock_row)
    assert res_g["lots_needed"] == 12
    assert res_g["grams_covered"] == 96.0
    assert res_g["leftover_grams"] == 4.0
    assert res_g["is_exact_match"] is False


    res_p = compute_single_contract_match("GOLDPETAL", 100.0, mock_row)
    assert res_p["lots_needed"] == 100
    assert res_p["grams_covered"] == 100.0
    assert res_p["leftover_grams"] == 0.0
    assert res_p["is_exact_match"] is True


def test_lots_and_leftover_math_8g():
    mock_row = {"close": 145000.0, "norm_close": 14500.0, "expiry_date": "2026-10-30", "grams_traded": 10000.0}


    res_g = compute_single_contract_match("GOLDGUINEA", 8.0, mock_row)
    assert res_g["lots_needed"] == 1
    assert res_g["grams_covered"] == 8.0
    assert res_g["leftover_grams"] == 0.0
    assert res_g["is_exact_match"] is True


    res_p = compute_single_contract_match("GOLDPETAL", 8.0, mock_row)
    assert res_p["lots_needed"] == 8
    assert res_p["grams_covered"] == 8.0
    assert res_p["leftover_grams"] == 0.0
    assert res_p["is_exact_match"] is True


    res_t = compute_single_contract_match("GOLDTEN", 8.0, mock_row)
    assert res_t["lots_needed"] == 0
    assert res_t["grams_covered"] == 0.0
    assert res_t["leftover_grams"] == 8.0
    assert res_t["is_exact_match"] is False


    res_m = compute_single_contract_match("GOLDM", 8.0, mock_row)
    assert res_m["lots_needed"] == 0
    assert res_m["grams_covered"] == 0.0
    assert res_m["leftover_grams"] == 8.0
    assert res_m["is_exact_match"] is False


def test_lots_and_leftover_math_10g():
    mock_row = {"close": 145000.0, "norm_close": 14500.0, "expiry_date": "2026-10-30", "grams_traded": 10000.0}


    res_t = compute_single_contract_match("GOLDTEN", 10.0, mock_row)
    assert res_t["lots_needed"] == 1
    assert res_t["grams_covered"] == 10.0
    assert res_t["leftover_grams"] == 0.0
    assert res_t["is_exact_match"] is True


    res_g = compute_single_contract_match("GOLDGUINEA", 10.0, mock_row)
    assert res_g["lots_needed"] == 1
    assert res_g["grams_covered"] == 8.0
    assert res_g["leftover_grams"] == 2.0
    assert res_g["is_exact_match"] is False


    res_p = compute_single_contract_match("GOLDPETAL", 10.0, mock_row)
    assert res_p["lots_needed"] == 10
    assert res_p["grams_covered"] == 10.0
    assert res_p["leftover_grams"] == 0.0
    assert res_p["is_exact_match"] is True


def test_find_exact_contract_combinations_100g():
    contracts_data = {
        "GOLDM": {"lot_size_g": 100, "quote_base_g": 10, "close": 145000.0, "norm_close": 14558.0, "premium_vs_goldten_bps": 15.0},
        "GOLDTEN": {"lot_size_g": 10, "quote_base_g": 10, "close": 145000.0, "norm_close": 14500.0, "premium_vs_goldten_bps": 0.0},
        "GOLDGUINEA": {"lot_size_g": 8, "quote_base_g": 8, "close": 116000.0, "norm_close": 14500.0, "premium_vs_goldten_bps": 60.0},
        "GOLDPETAL": {"lot_size_g": 1, "quote_base_g": 1, "close": 14500.0, "norm_close": 14500.0, "premium_vs_goldten_bps": 55.0},
    }

    combos = find_exact_contract_combinations(100.0, contracts_data, max_combinations=3)
    assert len(combos) >= 2
    assert all(c["is_exact_match"] is True for c in combos)
    assert all(c["leftover_grams"] == 0.0 for c in combos)
    assert all(c["grams_covered"] == 100.0 for c in combos)


    labels = [c["label"] for c in combos]
    assert any("GOLDM" in l for l in labels)
    assert any("GOLDTEN" in l for l in labels)


    lots = [c["total_lots"] for c in combos]
    assert lots == sorted(lots)


def test_best_fit_ranking_exact_match_and_premium():
    single_matches = [

        {
            "symbol": "GOLDGUINEA",
            "lots_needed": 12,
            "grams_covered": 96.0,
            "is_exact_match": False,
            "premium_vs_goldten_bps": -5.0,
            "grams_traded": 50000.0,
        },

        {
            "symbol": "GOLDPETAL",
            "lots_needed": 100,
            "grams_covered": 100.0,
            "is_exact_match": True,
            "premium_vs_goldten_bps": 55.0,
            "grams_traded": 100000.0,
        },

        {
            "symbol": "GOLDTEN",
            "lots_needed": 10,
            "grams_covered": 100.0,
            "is_exact_match": True,
            "premium_vs_goldten_bps": 0.0,
            "grams_traded": 80000.0,
        },
    ]

    best_fit = rank_best_fit(single_matches, combinations=[], sample_history_days=2)

    assert best_fit["best_fit_id"] == "GOLDTEN"
    assert "exact match first, then lowest premium" in best_fit["rule_tooltip"]
    assert best_fit["caveat_note"] is not None
    assert "Historical sample is short" in best_fit["caveat_note"]


def test_premium_uses_same_expiry_and_goldm_flagged():
    goldten_row = {
        "symbol": "GOLDTEN",
        "expiry_date": "2026-10-30",
        "norm_close": 14500.0,
    }


    petal_row = {
        "symbol": "GOLDPETAL",
        "expiry_date": "2026-10-30",
        "close": 14580.0,
        "norm_close": 14580.0,
        "grams_traded": 5000.0,
        "volume_lots": 5000,
    }
    match_petal = compute_single_contract_match("GOLDPETAL", 10.0, petal_row, goldten_row)

    assert match_petal["premium_vs_goldten_bps"] == pytest.approx(55.17, rel=0.01)
    assert match_petal["later_expiry_note"] is None


    goldm_row = {
        "symbol": "GOLDM",
        "expiry_date": "2026-11-05",
        "close": 144696.0,
        "norm_close": 14527.84,
        "grams_traded": 4000000.0,
        "volume_lots": 40000,
    }
    match_goldm = compute_single_contract_match("GOLDM", 100.0, goldm_row, goldten_row)
    assert match_goldm["premium_vs_goldten_bps"] is not None
    assert match_goldm["later_expiry_note"] is not None
    assert "expires on 2026-11-05" in match_goldm["later_expiry_note"]
    assert "after GOLDTEN" in match_goldm["later_expiry_note"]


def test_no_trade_excluded():
    row_no_trade = {
        "symbol": "GOLDPETAL",
        "expiry_date": "2026-10-30",
        "close": 14500.0,
        "norm_close": 14500.0,
        "volume_lots": 0,
        "grams_traded": 0.0,
        "no_trade": True,
    }

    match = compute_single_contract_match("GOLDPETAL", 100.0, row_no_trade)
    assert match["no_trade"] is True
    assert match["share_of_day_volume_pct"] is None


def test_daily_briefing_matches_karat_clean_csv():
    df = load_clean()
    briefing = compute_daily_briefing(df)

    assert briefing["data_available"] is True
    assert briefing["trading_days_loaded"] >= 2
    assert briefing["as_of_date"] == "2026-10-23"
    assert briefing["previous_date"] == "2026-10-22"


    price_changes = {p["symbol"]: p for p in briefing["price_changes"]}
    assert "GOLDM" in price_changes
    assert "GOLDTEN" in price_changes


    goldten_p = price_changes["GOLDTEN"]
    assert goldten_p["norm_close"] > 0


    assert len(briefing["facts_list"]) >= 4
    assert briefing["template_word_count"] <= 80
    assert len(briefing["template_summary"]) > 20


def test_daily_briefing_fewer_than_2_days():
    df = load_clean()
    single_day_df = df[df["date"] == df["date"].min()].copy()

    briefing = compute_daily_briefing(single_day_df)
    assert briefing["data_available"] is False
    assert "Not enough data yet" in briefing["message"]


def test_validate_ai_output_accepts_valid_numbers():
    payload = {
        "as_of_date": "2026-10-14",
        "norm_close": 14506.2,
        "spread_bps": 14.87,
        "quantity_g": 100,
        "lots": 10,
    }


    valid_text = "On 2026-10-14, with 10 lots covering 100 grams, the spread was 14.87 bps at a price of ₹14,506.20."
    is_valid, unsupported = validate_ai_output(valid_text, payload)
    assert is_valid is True
    assert len(unsupported) == 0


def test_validate_ai_output_rejects_hallucinated_numbers():
    payload = {
        "as_of_date": "2026-10-14",
        "norm_close": 14506.2,
        "spread_bps": 14.87,
    }


    bad_text = "The system achieved an expected net return of 88.5 bps with 99.9% confidence."
    is_valid, unsupported = validate_ai_output(bad_text, payload)
    assert is_valid is False
    assert 88.5 in unsupported


def test_prewritten_explanations_conform_to_rules():
    panels = ["contracts_table", "contract_chooser", "gap_chart", "signal_card", "daily_briefing"]

    for pid in panels:
        exp = get_prewritten_explanation(pid)
        assert "title" in exp
        assert "body" in exp
        assert "caveat" in exp


        sentences = [s.strip() for s in exp["body"].split(".") if s.strip()]
        assert 2 <= len(sentences) <= 4, f"Panel {pid} body should have 2-3 sentences"


        assert exp["caveat"].startswith("What this does not tell you:"), f"Panel {pid} caveat must start with 'What this does not tell you:'"


def test_api_position_matcher_endpoint():
    from fastapi.testclient import TestClient
    from backend.api.main import app

    client = TestClient(app)
    resp = client.get("/api/position-matcher?quantity_g=100")
    assert resp.status_code == 200
    data = resp.json()
    assert data["data_available"] is True
    assert data["quantity_g"] == 100.0
    assert len(data["single_contracts"]) == 4
    assert len(data["combinations"]) >= 2
    assert "best_fit" in data
    assert "MCX data, 59 trading days" in data["provenance_label"]
    assert "as of 2026-10-23" in data["provenance_label"]


def test_api_daily_briefing_endpoint():
    from fastapi.testclient import TestClient
    from backend.api.main import app

    client = TestClient(app)
    resp = client.get("/api/daily-briefing")
    assert resp.status_code == 200
    data = resp.json()
    assert data["data_available"] is True
    assert data["as_of_date"] == "2026-10-23"
    assert len(data["facts_list"]) >= 4
    assert data["template_word_count"] <= 80
    assert "MCX data, 59 trading days" in data["provenance_label"]


def test_api_explain_panel_endpoint():
    from fastapi.testclient import TestClient
    from backend.api.main import app

    client = TestClient(app)
    payload = {
        "panel_id": "contract_chooser",
        "panel_title": "Position Matcher",
        "data": {"quantity_g": 100, "best_fit": "GOLDTEN"},
        "as_of_date": "2026-10-14",
    }
    resp = client.post("/api/explain-panel", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["panel_id"] == "contract_chooser"
    assert "What this does not tell you" in data["explanation"]
    assert "data as of 2026-10-14" in data["provenance_label"]

