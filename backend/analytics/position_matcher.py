"""
KARAT – Contract Chooser & Position Matcher Analytics.

Deterministic calculation layer for:
1. Matching investor target quantity in grams to MCX gold futures contracts.
2. Computing exact lots, grams covered, leftover grams, and 999-equivalent purity.
3. Calculating contract value in Rs, common-scale cost, and premium vs GOLDTEN.
4. Finding exact contract combinations using fewest lots.
5. Determining 'Best fit' ranking by exact match, lowest premium, and liquidity.

All calculations live strictly in this data layer, never in UI components or AI prompts.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from backend.config import CONTRACTS, ContractSpec


def compute_single_contract_match(
    symbol: str,
    quantity_g: float,
    row: pd.Series | dict[str, Any],
    benchmark_goldten_row: Optional[pd.Series | dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Computes exact allocation, valuation, premium, and liquidity metrics
    for a single contract given target quantity in grams.
    """
    spec = CONTRACTS.get(symbol)
    if not spec:
        raise ValueError(f"Unknown contract symbol: {symbol}")

    lot_size_g = float(spec.lot_size_g)
    quote_base_g = float(spec.quote_base_g)
    purity = int(spec.purity)

    # 1. Lots and coverage maths
    # Floor integer lots to not overshoot the target quantity; leftover is uncovered remainder
    if quantity_g <= 0:
        lots_needed = 0
    else:
        lots_needed = int(quantity_g // lot_size_g)

    grams_covered = lots_needed * lot_size_g
    leftover_grams = round(quantity_g - grams_covered, 4)
    is_exact_match = (leftover_grams == 0.0 and lots_needed > 0) or (quantity_g == 0 and lots_needed == 0)

    # 2. Contract value in Rs
    # Formula: lots x lot grams x close / quote base
    close_price = float(row.get("close", 0.0) or 0.0)
    contract_value_rs = round(lots_needed * lot_size_g * (close_price / quote_base_g), 2)

    # 3. Cost per gram on common scale (norm_close)
    norm_close = float(row.get("norm_close", 0.0) or 0.0)

    # 4. Premium vs GOLDTEN of same expiry in bps
    premium_vs_goldten_bps: Optional[float] = None
    later_expiry_note: Optional[str] = None
    contract_expiry = str(row.get("expiry_date", "") or "")

    if benchmark_goldten_row is not None:
        goldten_norm_close = float(benchmark_goldten_row.get("norm_close", 0.0) or 0.0)
        goldten_expiry = str(benchmark_goldten_row.get("expiry_date", "") or "")

        if goldten_norm_close > 0 and norm_close > 0:
            premium_vs_goldten_bps = round(
                ((norm_close - goldten_norm_close) / goldten_norm_close) * 10_000.0,
                2
            )

        if symbol == "GOLDM" and contract_expiry and goldten_expiry and contract_expiry != goldten_expiry:
            later_expiry_note = (
                f"GOLDM expires on {contract_expiry}, which is after GOLDTEN ({goldten_expiry}). "
                "A later expiry carries cost of carry (financing & storage) explaining part of any positive gap."
            )

    # 5. Liquidity & Trading Activity
    grams_traded = float(row.get("grams_traded", 0.0) or 0.0)
    oi_lots = int(row.get("oi_lots", 0) or 0)
    volume_lots = int(row.get("volume_lots", 0) or 0)
    no_trade = bool(row.get("no_trade", False) or volume_lots == 0)

    share_of_day_volume_pct: Optional[float] = None
    if not no_trade and grams_traded > 0 and grams_covered > 0:
        share_of_day_volume_pct = round((grams_covered / grams_traded) * 100.0, 4)

    # 6. Expiry countdown & near expiry flag
    days_to_expiry = int(row.get("days_to_expiry", 0) or 0)
    is_near_expiry = days_to_expiry <= 3

    # 7. 999-equivalent grams detail row
    # GOLDM is 995 fineness, others are 999
    equiv_999_grams = round(grams_covered * (purity / 999.0), 4)
    if purity < 999:
        equiv_999_note = (
            f"{symbol} lots are {purity} fineness ({purity/10:.1f}% pure). "
            f"{grams_covered:g}g of {symbol} delivers {equiv_999_grams:.2f}g of 999 fine gold benchmark."
        )
    else:
        equiv_999_note = f"{symbol} is 999 fineness (benchmark purity). 100% equivalent to 999 fine gold."

    return {
        "symbol": symbol,
        "lot_size_g": lot_size_g,
        "quote_base_g": quote_base_g,
        "purity": purity,
        "expiry_date": contract_expiry,
        "days_to_expiry": days_to_expiry,
        "is_near_expiry": is_near_expiry,
        "lots_needed": lots_needed,
        "grams_covered": grams_covered,
        "leftover_grams": leftover_grams,
        "is_exact_match": is_exact_match,
        "close": close_price,
        "contract_value_rs": contract_value_rs,
        "norm_close": norm_close,
        "premium_vs_goldten_bps": premium_vs_goldten_bps,
        "later_expiry_note": later_expiry_note,
        "volume_lots": volume_lots,
        "grams_traded": grams_traded,
        "oi_lots": oi_lots,
        "share_of_day_volume_pct": share_of_day_volume_pct,
        "no_trade": no_trade,
        "equiv_999_grams": equiv_999_grams,
        "equiv_999_note": equiv_999_note,
    }


def find_exact_contract_combinations(
    quantity_g: float,
    contracts_data: dict[str, dict[str, Any]],
    max_combinations: int = 3,
) -> list[dict[str, Any]]:
    """
    Finds up to max_combinations combinations of contracts that hit quantity_g
    EXACTLY (leftover == 0) using the fewest total lots.

    For example:
    - 100 g: 1 GOLDM (1 lot), or 10 GOLDTEN (10 lots), or 12 GUINEA + 4 PETAL (16 lots)
    - 10 g: 1 GOLDTEN (1 lot), or 1 GUINEA + 2 PETAL (3 lots), or 10 PETAL (10 lots)
    - 8 g: 1 GUINEA (1 lot), or 8 PETAL (8 lots)
    """
    target = int(round(quantity_g))
    if target <= 0:
        return []

    # Available denominations from contracts
    # Order: GOLDM (100g), GOLDTEN (10g), GOLDGUINEA (8g), GOLDPETAL (1g)
    specs = [
        ("GOLDM", 100),
        ("GOLDTEN", 10),
        ("GOLDGUINEA", 8),
        ("GOLDPETAL", 1),
    ]

    # Filter to only contracts present in contracts_data
    available = [(sym, size) for sym, size in specs if sym in contracts_data]
    if not available:
        return []

    valid_solutions: list[dict[str, int]] = []

    # Exact coin-change search with branch & bound to find fewest lots
    # Max bounds for each denomination
    m_size = 100 if any(s == "GOLDM" for s, _ in available) else 0
    t_size = 10 if any(s == "GOLDTEN" for s, _ in available) else 0
    g_size = 8 if any(s == "GOLDGUINEA" for s, _ in available) else 0
    p_size = 1 if any(s == "GOLDPETAL" for s, _ in available) else 0

    max_m = (target // m_size) if m_size > 0 else 0

    for m in range(max_m, -1, -1):
        rem_m = target - (m * m_size)
        max_t = (rem_m // t_size) if t_size > 0 else 0
        for t in range(max_t, -1, -1):
            rem_t = rem_m - (t * t_size)
            max_g = (rem_t // g_size) if g_size > 0 else 0
            for g in range(max_g, -1, -1):
                rem_g = rem_t - (g * g_size)
                p = rem_g if p_size == 1 else 0
                if (m * m_size + t * t_size + g * g_size + p * p_size) == target:
                    sol: dict[str, int] = {}
                    if m > 0: sol["GOLDM"] = m
                    if t > 0: sol["GOLDTEN"] = t
                    if g > 0: sol["GOLDGUINEA"] = g
                    if p > 0: sol["GOLDPETAL"] = p
                    if sol:
                        valid_solutions.append(sol)

    # Sort solutions by total lots ascending, then diversity
    valid_solutions.sort(key=lambda s: (sum(s.values()), len(s)))

    # Select up to max_combinations diverse solutions (prefer distinct primary contract when possible)
    selected_solutions: list[dict[str, int]] = []
    seen_signatures = set()

    # Prioritize single-contract pure solutions first if they exist
    single_contract_sols = [s for s in valid_solutions if len(s) == 1]
    multi_contract_sols = [s for s in valid_solutions if len(s) > 1]

    for s in single_contract_sols + multi_contract_sols:
        sig = tuple(sorted(s.items()))
        if sig not in seen_signatures:
            seen_signatures.add(sig)
            selected_solutions.append(s)
            if len(selected_solutions) >= max_combinations:
                break

    # Format the combinations into complete analytical objects
    results: list[dict[str, Any]] = []
    for idx, sol in enumerate(selected_solutions, start=1):
        total_lots = sum(sol.values())
        total_covered_g = 0.0
        total_value_rs = 0.0
        weighted_norm_close_sum = 0.0
        weighted_premium_sum = 0.0
        components: list[dict[str, Any]] = []

        for sym, lots in sol.items():
            c_info = contracts_data[sym]
            c_lot_g = c_info["lot_size_g"]
            c_covered = lots * c_lot_g
            c_close = c_info["close"]
            c_quote_base = c_info["quote_base_g"]
            c_val = lots * c_lot_g * (c_close / c_quote_base)
            c_norm = c_info["norm_close"]
            c_prem = c_info.get("premium_vs_goldten_bps") or 0.0

            total_covered_g += c_covered
            total_value_rs += c_val
            weighted_norm_close_sum += c_norm * c_covered
            weighted_premium_sum += c_prem * c_covered

            components.append({
                "symbol": sym,
                "lots": lots,
                "grams": c_covered,
                "value_rs": round(c_val, 2),
                "norm_close": c_norm,
                "premium_bps": c_prem,
            })

        avg_norm_close = round(weighted_norm_close_sum / total_covered_g, 2) if total_covered_g > 0 else 0.0
        avg_premium_bps = round(weighted_premium_sum / total_covered_g, 2) if total_covered_g > 0 else 0.0

        label_parts = [f"{lots} {sym}" for sym, lots in sol.items()]
        label = " + ".join(label_parts)

        results.append({
            "combination_id": f"combo_{idx}",
            "label": label,
            "total_lots": total_lots,
            "grams_covered": total_covered_g,
            "leftover_grams": 0.0,
            "is_exact_match": True,
            "total_value_rs": round(total_value_rs, 2),
            "weighted_norm_close": avg_norm_close,
            "weighted_premium_bps": avg_premium_bps,
            "components": components,
        })

    return results


def rank_best_fit(
    single_matches: list[dict[str, Any]],
    combinations: list[dict[str, Any]],
    sample_history_days: int = 2,
) -> dict[str, Any]:
    """
    Determines 'Best fit' by:
    1. Exact match first (leftover == 0)
    2. Lowest premium vs GOLDTEN (lowest bps)
    3. Most liquid (grams_traded descending)

    Generates explanation tooltip and caveats for small premium differences or short history.
    """
    # Identify benchmark expiry if available
    benchmark_expiry = next((s.get("expiry_date", "") for s in single_matches if s.get("symbol") == "GOLDTEN"), "")
    candidates: list[dict[str, Any]] = []

    for s in single_matches:
        if s["lots_needed"] > 0:
            exp = s.get("expiry_date", "")
            prem = s["premium_vs_goldten_bps"] if s.get("premium_vs_goldten_bps") is not None else 0.0
            carry_adj = 0.0
            if exp and benchmark_expiry and exp != benchmark_expiry:
                try:
                    d_c = dt.datetime.strptime(exp, "%Y-%m-%d").date()
                    d_g = dt.datetime.strptime(benchmark_expiry, "%Y-%m-%d").date()
                    days_diff = (d_c - d_g).days
                    if days_diff > 0:
                        carry_adj = 600.0 * (days_diff / 365.0)
                except Exception:
                    carry_adj = 0.0

            total_lots = s["lots_needed"]
            lot_friction = max(0.0, (total_lots - 1) * 0.5)
            carry_adjusted_prem = prem - carry_adj
            effective_score = carry_adjusted_prem + lot_friction

            candidates.append({
                "type": "single",
                "id": s["symbol"],
                "display_name": f"{s['lots_needed']}x {s['symbol']}",
                "is_exact_match": s["is_exact_match"],
                "premium_bps": prem,
                "effective_score": effective_score,
                "liquidity_grams": s.get("grams_traded", 0.0),
                "total_lots": total_lots,
                "details": s,
            })

    for c in combinations:
        # Liquidity for a combo is minimum liquidity among components
        min_liq = min((c_comp["lots"] * 1000.0) for c_comp in c["components"])
        total_lots = c["total_lots"]
        lot_friction = max(0.0, (total_lots - 1) * 0.5)
        prem = c["weighted_premium_bps"]
        effective_score = prem + lot_friction

        candidates.append({
            "type": "combination",
            "id": c["combination_id"],
            "display_name": c["label"],
            "is_exact_match": True,
            "premium_bps": prem,
            "effective_score": effective_score,
            "liquidity_grams": min_liq,
            "total_lots": total_lots,
            "details": c,
        })

    if not candidates:
        return {
            "best_fit_id": None,
            "best_fit_label": "None",
            "rule_tooltip": "No suitable candidates matching target quantity.",
            "caveat_note": None,
        }

    # Sorting hierarchy:
    # 1. Exact match (True before False -> 0 for True, 1 for False)
    # 2. Lowest effective score (carry-adjusted premium + execution friction)
    # 3. Liquidity descending (higher grams_traded is better)
    # 4. Total lots ascending (fewer lots to minimize order tickets)
    sorted_candidates = sorted(
        candidates,
        key=lambda x: (
            0 if x["is_exact_match"] else 1,
            round(x["effective_score"], 2),
            -x["liquidity_grams"],
            x["total_lots"],
        )
    )

    best = sorted_candidates[0]

    # Check if premium differences are small (< 10 bps) among exact matches
    exact_matches = [c for c in candidates if c["is_exact_match"]]
    caveat_notes: list[str] = []

    if len(exact_matches) > 1:
        premiums = [c["premium_bps"] for c in exact_matches]
        prem_diff = max(premiums) - min(premiums)
        if prem_diff < 10.0:
            caveat_notes.append(f"Premium difference across contracts is small ({prem_diff:.1f} bps).")

    if sample_history_days < 40:
        caveat_notes.append(f"Historical sample is short ({sample_history_days} trading days).")

    rule_tooltip = "Best fit chosen by: exact match first, then lowest premium vs GOLDTEN (accounting for carry and execution friction across multiple lots), then liquidity."
    caveat_str = " ".join(caveat_notes) if caveat_notes else None

    return {
        "best_fit_id": best["id"],
        "best_fit_label": best["display_name"],
        "best_fit_type": best["type"],
        "rule_tooltip": rule_tooltip,
        "caveat_note": caveat_str,
        "ranked_candidates": [
            {
                "id": c["id"],
                "label": c["display_name"],
                "is_exact_match": c["is_exact_match"],
                "premium_bps": c["premium_bps"],
                "effective_score": round(c["effective_score"], 2),
                "total_lots": c["total_lots"],
                "liquidity_grams": c["liquidity_grams"],
            }
            for c in sorted_candidates
        ],
    }


def compute_position_matcher(
    df: pd.DataFrame,
    quantity_g: float = 100.0,
    target_expiry: Optional[str] = None,
    as_of_date: Optional[str] = None,
) -> dict[str, Any]:
    """
    Main entry point for Position Matcher computation on real MCX Bhavcopy dataframe.
    Evaluates:
    - Nearest expiry month with > 3 days left (default)
    - Single contract allocations for GOLDM, GOLDTEN, GOLDGUINEA, GOLDPETAL
    - Top exact combinations hitting quantity_g exactly
    - Best fit ranking and disclosures
    """
    if df.empty:
        return {
            "data_available": False,
            "message": "Not enough data yet",
        }

    # Standardize column names and deduplicate
    work_df = df.copy()
    work_df.columns = [c.lower() for c in work_df.columns]
    work_df = work_df.loc[:, ~work_df.columns.duplicated()]

    # Determine as_of_date
    if not as_of_date:
        as_of_date = str(work_df["date"].max())[:10]

    day_df = work_df[work_df["date"].astype(str).str.startswith(as_of_date)].copy()
    if day_df.empty:
        return {
            "data_available": False,
            "message": f"No data found for date {as_of_date}",
        }

    # Determine unique expiry dates
    expiries = sorted(day_df["expiry_date"].astype(str).unique().tolist())

    # Expiry selection logic:
    # Nearest expiry with more than 3 days left
    valid_expiries = [
        exp for exp in expiries
        if int(day_df.loc[day_df["expiry_date"] == exp, "days_to_expiry"].iloc[0]) > 3
    ]

    selected_expiry = target_expiry if (target_expiry and target_expiry in expiries) else (valid_expiries[0] if valid_expiries else (expiries[0] if expiries else None))

    if not selected_expiry:
        return {
            "data_available": False,
            "message": "No valid contract expiries found",
        }

    # Benchmark GOLDTEN row for the selected expiry
    goldten_rows = day_df[(day_df["symbol"] == "GOLDTEN") & (day_df["expiry_date"] == selected_expiry)]
    goldten_benchmark = goldten_rows.iloc[0].to_dict() if not goldten_rows.empty else None

    # Compute single contract matches for each tracked symbol
    contracts_data: dict[str, dict[str, Any]] = {}
    single_matches: list[dict[str, Any]] = []

    for sym in ["GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"]:
        sym_rows = day_df[day_df["symbol"] == sym]
        if sym_rows.empty:
            continue

        # Find row for selected expiry or closest expiry
        matched_row = sym_rows[sym_rows["expiry_date"] == selected_expiry]
        if matched_row.empty:
            # If GOLDM has a different cycle (e.g. Nov 05 instead of Oct 30), pick its nearest cycle > 3 days
            valid_sym = sym_rows[sym_rows["days_to_expiry"] > 3]
            matched_row = valid_sym.iloc[0:1] if not valid_sym.empty else sym_rows.iloc[0:1]

        row_dict = matched_row.iloc[0].to_dict()
        match_result = compute_single_contract_match(
            symbol=sym,
            quantity_g=quantity_g,
            row=row_dict,
            benchmark_goldten_row=goldten_benchmark,
        )
        contracts_data[sym] = match_result
        single_matches.append(match_result)

    # Combinations (up to 3 exact matches)
    combinations = find_exact_contract_combinations(
        quantity_g=quantity_g,
        contracts_data=contracts_data,
        max_combinations=3,
    )

    # Total trading days loaded
    trading_days_loaded = work_df["date"].nunique()

    # Best fit ranking
    best_fit = rank_best_fit(
        single_matches=single_matches,
        combinations=combinations,
        sample_history_days=trading_days_loaded,
    )

    return {
        "data_available": True,
        "as_of_date": as_of_date,
        "trading_days_loaded": trading_days_loaded,
        "provenance_label": f"MCX data, {trading_days_loaded} trading days, as of {as_of_date}",
        "quantity_g": quantity_g,
        "selected_expiry": selected_expiry,
        "available_expiries": expiries,
        "single_contracts": single_matches,
        "combinations": combinations,
        "best_fit": best_fit,
        "compliance_disclaimer": "Reference for investment",
    }
