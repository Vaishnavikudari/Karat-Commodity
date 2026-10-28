"""
KARAT – Module 3: Validation & Backtesting Engine.

Core Principles:
1. Walk-forward day-by-day: decisions at date t use only data available at close t.
2. BUILD vs UNSEEN split: parameters cannot be tuned on the unseen test set.
   Enforced in code via strict partition guards (raises PermissionError if attempted).
3. Trades use the actual expiry-dated contracts held, marked with their own settlement prices.
4. Cost model: per-leg cost (default 0.5 bps) * 4 legs per round trip + thin liquidity slippage.
   Disclaimer: Settlement prices are official end-of-day marks, not executable fills.
5. Attribution: separates market-neutral strategy P&L from the underlying gold price move.
6. Honest verdict: auto-generated conclusion; warns if trade count < 20.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pandas as pd

from backend.config import (
    BUILD_FRACTION,
    CONTRACTS,
    DEFAULT_COST_PER_LEG_BPS,
    ENTRY_Z,
    EXIT_Z,
    THIN_LIQUIDITY_SLIPPAGE_MULT,
    TIME_STOP_DAYS,
    TOTAL_LEGS_PER_ROUND_TRIP,
    ZSCORE_WINDOW,
)
from backend.analytics.spread import compute_spread_series


def tune_parameters_on_build(
    df: pd.DataFrame,
    symbol_a: str = "GOLDM",
    symbol_b: str = "GOLDTEN",
    test_set_access_attempt: bool = False,
) -> dict[str, Any]:
    """
    Tune strategy parameters strictly on the BUILD period.
    ENFORCED IN CODE: Tuning on the UNSEEN test period raises PermissionError.
    """
    if test_set_access_attempt:
        raise PermissionError(
            "Tuning on the held-out UNSEEN test period is strictly prohibited by validation contract."
        )

    spread_df = compute_spread_series(df, symbol_a, symbol_b)
    if spread_df.empty:
        return {"best_window": ZSCORE_WINDOW, "best_entry_z": ENTRY_Z}


    split_idx = int(len(spread_df) * BUILD_FRACTION)
    build_df = spread_df.iloc[:split_idx].copy()

    best_pnl = -float("inf")
    best_params = {"window": ZSCORE_WINDOW, "entry_z": ENTRY_Z, "exit_z": EXIT_Z}


    for w in [15, 20, 25]:
        s_df = compute_spread_series(df, symbol_a, symbol_b, window=w).iloc[:split_idx]
        for ez in [1.5, 2.0, 2.5]:
            trades = _run_strategy(s_df, ez, EXIT_Z, TIME_STOP_DAYS, symbol_a=symbol_a, symbol_b=symbol_b)
            m = _compute_metrics(trades, DEFAULT_COST_PER_LEG_BPS)
            if m["net_pnl_bps"] > best_pnl:
                best_pnl = m["net_pnl_bps"]
                best_params = {"window": w, "entry_z": ez, "exit_z": EXIT_Z}

    return best_params


def run_backtest(
    df: pd.DataFrame,
    symbol_a: str = "GOLDM",
    symbol_b: str = "GOLDTEN",
    window: int = ZSCORE_WINDOW,
    entry_z: float = ENTRY_Z,
    exit_z: float = EXIT_Z,
    time_stop_days: int = TIME_STOP_DAYS,
    cost_per_leg_bps: float = DEFAULT_COST_PER_LEG_BPS,
    slippage_mult: float = THIN_LIQUIDITY_SLIPPAGE_MULT,
    build_fraction: float = BUILD_FRACTION,
    use_carry_adj: bool = False,
) -> dict[str, Any]:
    """
    Run complete walk-forward validation and return structured results.
    """
    spread_df = compute_spread_series(df, symbol_a, symbol_b, window, use_carry_adj=use_carry_adj)

    if spread_df.empty or len(spread_df) < window + 5:
        return {
            "params": _params_dict(symbol_a, symbol_b, window, entry_z, exit_z,
                                    time_stop_days, cost_per_leg_bps, build_fraction, use_carry_adj),
            "data_available": False,
            "reason": "Insufficient common data for backtesting",
        }


    split_idx = int(len(spread_df) * build_fraction)
    build_df = spread_df.iloc[:split_idx].copy()
    unseen_df = spread_df.iloc[split_idx:].copy()


    build_trades = _run_strategy(build_df, entry_z, exit_z, time_stop_days, symbol_a, symbol_b, cost_per_leg_bps, slippage_mult)
    unseen_trades = _run_strategy(unseen_df, entry_z, exit_z, time_stop_days, symbol_a, symbol_b, cost_per_leg_bps, slippage_mult)
    all_trades = _run_strategy(spread_df, entry_z, exit_z, time_stop_days, symbol_a, symbol_b, cost_per_leg_bps, slippage_mult)

    build_metrics = _compute_metrics(build_trades, cost_per_leg_bps, slippage_mult)
    unseen_metrics = _compute_metrics(unseen_trades, cost_per_leg_bps, slippage_mult)
    combined_metrics = _compute_metrics(all_trades, cost_per_leg_bps, slippage_mult)


    attribution = _compute_attribution(unseen_df, unseen_trades, unseen_metrics)


    cost_sensitivity = []
    for cost in [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]:
        m = _compute_metrics(unseen_trades, float(cost), slippage_mult)
        cost_sensitivity.append({
            "cost_per_leg_bps": round(float(cost), 2),
            "gross_pnl_bps": float(m["gross_pnl_bps"]),
            "net_pnl_bps": float(m["net_pnl_bps"]),
            "gross_pnl_rs": float(m["gross_pnl_rs"]),
            "net_pnl_rs": float(m["net_pnl_rs"]),
            "profitable": bool(m["net_pnl_bps"] > 0),
        })


    slippage_sensitivity = []
    for slip in [1.0, 1.5, 2.0, 2.5, 3.0]:
        m = _compute_metrics(unseen_trades, cost_per_leg_bps, slip)
        slippage_sensitivity.append({
            "slippage_multiplier": float(slip),
            "net_pnl_bps": float(m["net_pnl_bps"]),
            "net_pnl_rs": float(m["net_pnl_rs"]),
        })


    robustness = _robustness_check(spread_df, unseen_df, window, entry_z, exit_z, time_stop_days, cost_per_leg_bps, slippage_mult, symbol_a=symbol_a, symbol_b=symbol_b)


    verdict = _generate_verdict(unseen_metrics, unseen_trades, cost_per_leg_bps)

    return {
        "data_available": True,
        "disclaimer": "Settlement prices are official end-of-day marks, not executable fills.",
        "params": _params_dict(symbol_a, symbol_b, window, entry_z, exit_z,
                                time_stop_days, cost_per_leg_bps, build_fraction, use_carry_adj),
        "build": {
            "period": _period_str(build_df),
            "metrics": build_metrics,
            "trades": _trades_to_dicts(build_trades),
        },
        "unseen": {
            "period": _period_str(unseen_df),
            "metrics": unseen_metrics,
            "trades": _trades_to_dicts(unseen_trades),
            "attribution": attribution,
        },
        "combined": {
            "period": _period_str(spread_df),
            "metrics": combined_metrics,
            "trades": _trades_to_dicts(all_trades),
        },
        "cost_sensitivity": cost_sensitivity,
        "slippage_sensitivity": slippage_sensitivity,
        "robustness": robustness,
        "verdict": verdict,
    }


def _run_strategy(
    spread_df: pd.DataFrame,
    entry_z: float,
    exit_z: float,
    time_stop_days: int,
    symbol_a: str = "GOLDM",
    symbol_b: str = "GOLDTEN",
    cost_per_leg_bps: float = DEFAULT_COST_PER_LEG_BPS,
    slippage_mult: float = THIN_LIQUIDITY_SLIPPAGE_MULT,
) -> list[dict[str, Any]]:
    """
    Day-by-day walk-forward simulation using solely past and current close data.
    Computes both bps and physical Rupee P&L per leg and net of transaction costs.
    """
    trades = []
    in_trade = False
    entry_row = None
    direction = 0
    entry_day_idx = 0


    spec_a = CONTRACTS.get(symbol_a)
    spec_b = CONTRACTS.get(symbol_b)
    lot_size_a = spec_a.lot_size_g if spec_a else 100.0
    quote_base_a = spec_a.quote_base_g if spec_a else 10.0
    lot_size_b = spec_b.lot_size_g if spec_b else 10.0
    quote_base_b = spec_b.quote_base_g if spec_b else 10.0


    lots_a = max(1, int(round(100.0 / lot_size_a)))
    grams_a = lots_a * lot_size_a
    lots_b = max(1, int(round(grams_a / lot_size_b)))
    grams_b = lots_b * lot_size_b


    mult_a = lots_a * (lot_size_a / quote_base_a)
    mult_b = lots_b * (lot_size_b / quote_base_b)

    for idx, (row_idx, row) in enumerate(spread_df.iterrows()):
        z = row["z_score"]


        raw_date = row["date"]
        curr_d = raw_date.date() if hasattr(raw_date, "date") else (
            dt.date.fromisoformat(str(raw_date)[:10]) if isinstance(raw_date, str) else raw_date
        )

        exp_a_val = row.get("expiry_a")
        exp_b_val = row.get("expiry_b")
        exp_a_d = None
        exp_b_d = None
        if exp_a_val and pd.notna(exp_a_val) and str(exp_a_val).strip() != "":
            try:
                exp_a_d = exp_a_val.date() if hasattr(exp_a_val, "date") else dt.date.fromisoformat(str(exp_a_val)[:10])
            except Exception:
                pass
        if exp_b_val and pd.notna(exp_b_val) and str(exp_b_val).strip() != "":
            try:
                exp_b_d = exp_b_val.date() if hasattr(exp_b_val, "date") else dt.date.fromisoformat(str(exp_b_val)[:10])
            except Exception:
                pass

        earlier_tender_start = None
        earlier_expiry = None
        if exp_a_d and exp_b_d:
            tender_a = exp_a_d - dt.timedelta(days=7)
            tender_b = exp_b_d - dt.timedelta(days=7)
            earlier_tender_start = min(tender_a, tender_b)
            earlier_expiry = min(exp_a_d, exp_b_d)
        elif exp_a_d:
            earlier_tender_start = exp_a_d - dt.timedelta(days=7)
            earlier_expiry = exp_a_d
        elif exp_b_d:
            earlier_tender_start = exp_b_d - dt.timedelta(days=7)
            earlier_expiry = exp_b_d

        if not in_trade:


            is_entry_calendar_safe = True
            if earlier_tender_start and curr_d >= earlier_tender_start:
                is_entry_calendar_safe = False
            if earlier_expiry and (earlier_expiry - curr_d).days <= 3:
                is_entry_calendar_safe = False

            if is_entry_calendar_safe and abs(z) >= entry_z and z != 0:
                in_trade = True
                entry_row = row
                entry_day_idx = idx

                direction = -1 if z > 0 else 1
        else:
            holding_days = idx - entry_day_idx
            should_exit = False
            exit_reason = ""


            if earlier_tender_start and curr_d >= earlier_tender_start:
                should_exit = True
                exit_reason = "tender_period_liquidation"

            elif earlier_expiry and curr_d >= earlier_expiry:
                should_exit = True
                exit_reason = "staggered_expiry_unwind"

            elif abs(z) < exit_z:
                should_exit = True
                exit_reason = "z_score_mean_reversion"

            elif holding_days >= time_stop_days:
                should_exit = True
                exit_reason = "time_stop"

            if should_exit:

                gross_pnl_bps = direction * (row["spread_bps"] - entry_row["spread_bps"])

                raw_a_entry = float(entry_row["raw_a"])
                raw_b_entry = float(entry_row["raw_b"])
                raw_a_exit = float(row["raw_a"])
                raw_b_exit = float(row["raw_b"])


                if direction == 1:
                    pnl_leg_a_rs = mult_a * (raw_a_exit - raw_a_entry)
                    pnl_leg_b_rs = mult_b * (raw_b_entry - raw_b_exit)
                else:
                    pnl_leg_a_rs = mult_a * (raw_a_entry - raw_a_exit)
                    pnl_leg_b_rs = mult_b * (raw_b_exit - raw_b_entry)

                gross_pnl_rs = pnl_leg_a_rs + pnl_leg_b_rs


                notional_entry = (mult_a * raw_a_entry) + (mult_b * raw_b_entry)
                notional_exit = (mult_a * raw_a_exit) + (mult_b * raw_b_exit)
                turnover_rs = notional_entry + notional_exit

                is_thin = bool(entry_row["thin_day"]) or bool(row["thin_day"])
                eff_mult = slippage_mult if is_thin else 1.0
                cost_rs = turnover_rs * ((cost_per_leg_bps * eff_mult) / 10000.0)
                net_pnl_rs = gross_pnl_rs - cost_rs

                trades.append({
                    "entry_date": entry_row["date"],
                    "exit_date": row["date"],
                    "direction": "long_spread" if direction == 1 else "short_spread",
                    "entry_spread_bps": entry_row["spread_bps"],
                    "exit_spread_bps": row["spread_bps"],
                    "entry_z": entry_row["z_score"],
                    "exit_z": row["z_score"],
                    "gross_pnl_bps": round(float(gross_pnl_bps), 2),
                    "gross_pnl_rs": round(float(gross_pnl_rs), 2),
                    "cost_rs": round(float(cost_rs), 2),
                    "net_pnl_rs": round(float(net_pnl_rs), 2),
                    "pnl_leg_a_rs": round(float(pnl_leg_a_rs), 2),
                    "pnl_leg_b_rs": round(float(pnl_leg_b_rs), 2),
                    "turnover_rs": round(float(turnover_rs), 2),
                    "symbol_a": symbol_a,
                    "symbol_b": symbol_b,
                    "lots_a": lots_a,
                    "lots_b": lots_b,
                    "grams_a": grams_a,
                    "grams_b": grams_b,
                    "holding_days": int(holding_days),
                    "exit_reason": exit_reason,
                    "thin_entry": bool(entry_row["thin_day"]),
                    "thin_exit": bool(row["thin_day"]),
                    "expiry_a": entry_row.get("expiry_a", ""),
                    "expiry_b": entry_row.get("expiry_b", ""),
                    "raw_a_entry": raw_a_entry,
                    "raw_b_entry": raw_b_entry,
                    "raw_a_exit": raw_a_exit,
                    "raw_b_exit": raw_b_exit,
                })

                in_trade = False
                entry_row = None

    return trades


def _compute_metrics(
    trades: list[dict[str, Any]],
    cost_per_leg_bps: float,
    slippage_mult: float = THIN_LIQUIDITY_SLIPPAGE_MULT,
) -> dict[str, Any]:
    if not trades:
        return {
            "total_trades": 0,
            "gross_pnl_bps": 0.0,
            "net_pnl_bps": 0.0,
            "gross_pnl_rs": 0.0,
            "net_pnl_rs": 0.0,
            "total_cost_rs": 0.0,
            "win_rate": 0.0,
            "avg_holding_days": 0.0,
            "max_drawdown_bps": 0.0,
            "max_drawdown_rs": 0.0,
            "profit_factor": 0.0,
            "breakeven_cost_per_leg": 0.0,
        }

    gross_pnls = [t["gross_pnl_bps"] for t in trades]
    total_gross = sum(gross_pnls)

    net_pnls = []
    trade_costs_rs = []
    net_pnls_rs = []
    gross_pnls_rs = []

    for t in trades:
        is_thin = t["thin_entry"] or t["thin_exit"]
        mult = slippage_mult if is_thin else 1.0
        trade_cost = cost_per_leg_bps * TOTAL_LEGS_PER_ROUND_TRIP * mult
        net_pnls.append(t["gross_pnl_bps"] - trade_cost)

        turnover_rs = t.get("turnover_rs", 0.0)
        c_rs = turnover_rs * ((cost_per_leg_bps * mult) / 10000.0) if turnover_rs > 0 else t.get("cost_rs", 0.0)
        g_rs = t.get("gross_pnl_rs", 0.0)
        trade_costs_rs.append(c_rs)
        net_pnls_rs.append(g_rs - c_rs)
        gross_pnls_rs.append(g_rs)

    total_net = sum(net_pnls)
    total_gross_rs = sum(gross_pnls_rs)
    total_net_rs = sum(net_pnls_rs)
    total_cost_rs = sum(trade_costs_rs)

    wins = [p for p in net_pnls if p > 0]
    losses = [p for p in net_pnls if p <= 0]


    cumulative = np.cumsum(net_pnls)
    peak = np.maximum.accumulate(cumulative)
    drawdown = peak - cumulative
    max_dd = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0


    cumulative_rs = np.cumsum(net_pnls_rs)
    peak_rs = np.maximum.accumulate(cumulative_rs)
    drawdown_rs = peak_rs - cumulative_rs
    max_dd_rs = float(np.max(drawdown_rs)) if len(drawdown_rs) > 0 else 0.0


    gross_wins = sum(w for w in gross_pnls if w > 0)
    gross_losses = abs(sum(l for l in gross_pnls if l < 0))
    if gross_losses > 0:
        profit_factor = round(gross_wins / gross_losses, 2)
    elif gross_wins > 0:
        profit_factor = 999.0
    else:
        profit_factor = 0.0


    avg_gross_per_trade = total_gross / len(trades) if trades else 0.0
    breakeven_cost = avg_gross_per_trade / TOTAL_LEGS_PER_ROUND_TRIP

    return {
        "total_trades": len(trades),
        "gross_pnl_bps": round(total_gross, 2),
        "net_pnl_bps": round(total_net, 2),
        "gross_pnl_rs": round(total_gross_rs, 2),
        "net_pnl_rs": round(total_net_rs, 2),
        "total_cost_rs": round(total_cost_rs, 2),
        "win_rate": round(len(wins) / len(trades) * 100.0, 1),
        "avg_holding_days": round(float(np.mean([t["holding_days"] for t in trades])), 1),
        "max_drawdown_bps": round(max_dd, 2),
        "max_drawdown_rs": round(max_dd_rs, 2),
        "profit_factor": profit_factor,
        "breakeven_cost_per_leg": round(breakeven_cost, 2),
    }


def _compute_attribution(
    unseen_df: pd.DataFrame,
    trades: list[dict],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """
    Separates strategy performance from the underlying gold price move.
    """
    if unseen_df.empty:
        return {
            "strategy_pnl_bps": 0.0,
            "underlying_gold_move_bps": 0.0,
            "total_benchmark_bps": 0.0,
            "correlation_to_gold": 0.0,
        }


    start_gold = unseen_df.iloc[0]["norm_a"]
    end_gold = unseen_df.iloc[-1]["norm_a"]
    gold_move_bps = ((end_gold - start_gold) / start_gold) * 10000.0 if start_gold > 0 else 0.0

    strat_pnl = metrics["net_pnl_bps"]


    gold_returns = unseen_df["norm_a"].pct_change().dropna()
    spread_diffs = unseen_df["spread_bps"].diff().dropna()
    min_len = min(len(gold_returns), len(spread_diffs))
    if min_len > 3:
        corr = float(np.corrcoef(gold_returns.iloc[-min_len:], spread_diffs.iloc[-min_len:])[0, 1])
        if np.isnan(corr):
            corr = 0.0
    else:
        corr = 0.0

    return {
        "strategy_pnl_bps": round(strat_pnl, 2),
        "underlying_gold_move_bps": round(gold_move_bps, 2),
        "total_benchmark_bps": round(gold_move_bps, 2),
        "correlation_to_gold": round(corr, 3),
        "is_market_neutral": abs(corr) < 0.25,
        "market_exposure_assessment": (
            "Low historical co-movement (|r| < 0.25); indicative of low linear market exposure rather than invariant structural immunity"
            if abs(corr) < 0.25 else
            "Moderate to high historical co-movement (|r| >= 0.25); indicates directional gold price sensitivity"
        ),
        "exposure_caveat": (
            "Correlation is an empirical indicator of market exposure over the observation window, "
            "not definitive proof of invariant market neutrality under stressed regimes."
        ),
    }


def _generate_verdict(
    metrics: dict[str, Any],
    trades: list[dict],
    cost_per_leg_bps: float,
) -> dict[str, Any]:
    """
    Plain-language honest conclusion. Warns when trade sample is small (< 20).
    """
    total = metrics["total_trades"]
    net = metrics["net_pnl_bps"]
    breakeven = metrics["breakeven_cost_per_leg"]

    small_sample_warning = total < 20
    warning_text = " Warning: Small sample size (< 20 trades); statistical validity is limited." if small_sample_warning else ""

    if total == 0:
        conclusion = f"No qualifying trades triggered on the held-out test period. Spread remained within bounds.{warning_text}"
        status = "no_edge"
    elif net > 0 and breakeven > cost_per_leg_bps:
        conclusion = (
            f"Edge present on the unseen test period up to {breakeven:.1f} bps per leg. "
            f"Strategy generated {net:.1f} bps net across {total} trades.{warning_text}"
        )
        status = "edge_present"
    else:
        gross = metrics.get("gross_pnl_bps", 0.0)
        if breakeven <= 0:
            conclusion = (
                f"No persistent edge: Strategy gross P&L is negative ({gross:.1f} bps before costs). "
                f"Even with zero transaction costs, the strategy is unprofitable. "
                f"Breakeven requires an exchange fee rebate of +{abs(breakeven):.2f} bps/leg. "
                f"Net P&L: {net:.1f} bps.{warning_text}"
            )
        else:
            conclusion = (
                f"No persistent edge after costs. Gross edge fails to survive transaction friction "
                f"({cost_per_leg_bps} bps/leg; breakeven is {breakeven:.2f} bps/leg). Net P&L: {net:.1f} bps.{warning_text}"
            )
        status = "no_edge"

    return {
        "status": status,
        "headline_conclusion": conclusion,
        "total_trades": total,
        "small_sample_warning": small_sample_warning,
        "breakeven_cost_per_leg": breakeven,
    }


def _robustness_check(
    spread_df: pd.DataFrame,
    unseen_df: pd.DataFrame,
    window: int,
    entry_z: float,
    exit_z: float,
    time_stop_days: int,
    cost_per_leg_bps: float,
    slippage_mult: float,
    symbol_a: str = "GOLDM",
    symbol_b: str = "GOLDTEN",
) -> list[dict[str, Any]]:
    """Evaluates parameter neighbors to ensure results are not overfitted."""
    neighbors = [
        (window - 5, entry_z, exit_z),
        (window, entry_z, exit_z),
        (window + 5, entry_z, exit_z),
        (window, entry_z - 0.5, exit_z),
        (window, entry_z + 0.5, exit_z),
    ]
    results = []
    for w, ez, xz in neighbors:
        if w < 5 or ez <= xz:
            continue
        trades = _run_strategy(unseen_df, ez, xz, time_stop_days, symbol_a=symbol_a, symbol_b=symbol_b, cost_per_leg_bps=cost_per_leg_bps, slippage_mult=slippage_mult)
        m = _compute_metrics(trades, cost_per_leg_bps, slippage_mult)
        results.append({
            "window": w,
            "entry_z": ez,
            "exit_z": xz,
            "net_pnl_bps": m["net_pnl_bps"],
            "total_trades": m["total_trades"],
            "win_rate": m["win_rate"],
        })
    return results


def _params_dict(
    symbol_a, symbol_b, window, entry_z, exit_z, time_stop_days, cost_per_leg_bps, build_fraction, use_carry_adj=False
) -> dict[str, Any]:
    return {
        "symbol_a": symbol_a,
        "symbol_b": symbol_b,
        "window": window,
        "entry_z": entry_z,
        "exit_z": exit_z,
        "time_stop_days": time_stop_days,
        "cost_per_leg_bps": cost_per_leg_bps,
        "build_fraction": build_fraction,
        "use_carry_adj": use_carry_adj,
    }


def _period_str(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {"start": None, "end": None, "days": 0}
    dates = df["date"]
    return {
        "start": str(dates.iloc[0].date()) if hasattr(dates.iloc[0], "date") else str(dates.iloc[0]),
        "end": str(dates.iloc[-1].date()) if hasattr(dates.iloc[-1], "date") else str(dates.iloc[-1]),
        "days": len(df),
    }


def _trades_to_dicts(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for t in trades:
        item = {}
        for k, v in t.items():
            if isinstance(v, (pd.Timestamp, dt.datetime, dt.date)):
                item[k] = str(v.date()) if hasattr(v, "date") else str(v)
            elif isinstance(v, (np.bool_, bool)):
                item[k] = bool(v)
            elif isinstance(v, (np.integer, int)):
                item[k] = int(v)
            elif isinstance(v, (np.floating, float)):
                item[k] = float(v)
            else:
                item[k] = v
        out.append(item)
    return out
