"""
KARAT – Opportunity & Risk Signal Engine.

Evaluates inter-contract spread dislocations against institutional constraints:
1. Normalized spread z-score threshold (|z| >= ENTRY_Z).
2. Economic viability: gross spread edge must exceed total round-trip costs
   (4 legs * cost_per_leg + thin liquidity penalty).
3. Liquidity check: neither contract may be in zero or severely thin liquidity.
4. Expiry / Calendar safety: minimum days-to-expiry buffer to avoid delivery/tender entrapment.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd

from backend.config import (
    CONTRACTS,
    ENTRY_Z,
    EXIT_Z,
    DEFAULT_COST_PER_LEG_BPS,
    TOTAL_LEGS_PER_ROUND_TRIP,
    THIN_LIQUIDITY_SLIPPAGE_MULT,
    VOLUME_THIN_THRESHOLD,
    OI_THIN_THRESHOLD,
    TRACKED_SYMBOLS,
)
from backend.analytics.spread import compute_spread_series, estimate_round_trip_cost


def evaluate_pair_signal(
    df: pd.DataFrame,
    symbol_a: str = "GOLDM",
    symbol_b: str = "GOLDTEN",
    window: int = 20,
    entry_z: float = ENTRY_Z,
    cost_per_leg_bps: float = DEFAULT_COST_PER_LEG_BPS,
) -> dict[str, Any]:
    """
    Evaluate if an actionable, economically positive spread opportunity exists today.
    Returns a structured signal object.
    """
    spread_df = compute_spread_series(df, symbol_a, symbol_b, window=window)
    if spread_df.empty or len(spread_df) < 5:
        latest_d = str(spread_df.iloc[-1]["date"].date()) if not spread_df.empty and hasattr(spread_df.iloc[-1]["date"], "date") else None
        latest_bps = float(spread_df.iloc[-1]["spread_bps"]) if not spread_df.empty else 0.0
        latest_rs = float(spread_df.iloc[-1]["spread_rupees"]) if not spread_df.empty else 0.0
        return {
            "has_signal": False,
            "signal_state": "none",
            "pair": f"{symbol_a}/{symbol_b}",
            "symbol_a": symbol_a,
            "symbol_b": symbol_b,
            "status": "neutral",
            "date": latest_d,
            "z_score": 0.0,
            "spread_bps": latest_bps,
            "spread_rupees": latest_rs,
            "action": "none",
            "cheap_contract": None,
            "rich_contract": None,
            "message": "Insufficient history to compute statistical z-score (< 15 trading days loaded).",
            "checks": {
                "is_gap_unusual": False,
                "is_cost_viable": False,
                "is_liquid": False,
                "is_expiry_safe": False,
            },
            "evaluated_at": dt.datetime.utcnow().isoformat(),
        }

    latest = spread_df.iloc[-1]
    z = float(latest["z_score"])
    spread_bps = float(latest["spread_bps"])
    spread_rupees = float(latest["spread_rupees"])
    thin = bool(latest["thin_day"])
    rt_cost_bps = estimate_round_trip_cost(cost_per_leg_bps, thin)


    z_breach = abs(z) >= entry_z


    expected_reversion_bps = abs(spread_bps) * (1.0 - (EXIT_Z / max(abs(z), 0.001))) if abs(z) > EXIT_Z else 0.0
    net_edge_bps = expected_reversion_bps - rt_cost_bps
    is_cost_viable = net_edge_bps > 0.0


    vol_a, vol_b = int(latest["vol_a"]), int(latest["vol_b"])
    oi_a, oi_b = int(latest["oi_a"]), int(latest["oi_b"])
    liq_pass = (vol_a > 0 and vol_b > 0) and (oi_a >= 10 and oi_b >= 10)


    today_date = latest["date"]
    exp_a_str = latest.get("expiry_a")
    exp_b_str = latest.get("expiry_b")
    days_to_exp_a = 999
    days_to_exp_b = 999

    try:
        if exp_a_str:
            d_a = dt.date.fromisoformat(str(exp_a_str)[:10])
            cur_d = today_date.date() if hasattr(today_date, "date") else today_date
            days_to_exp_a = (d_a - cur_d).days
        if exp_b_str:
            d_b = dt.date.fromisoformat(str(exp_b_str)[:10])
            cur_d = today_date.date() if hasattr(today_date, "date") else today_date
            days_to_exp_b = (d_b - cur_d).days
    except Exception:
        pass

    roll_risk = (days_to_exp_a <= 3 or days_to_exp_b <= 3)

    has_signal = z_breach and is_cost_viable and liq_pass and not roll_risk


    if z > 0:
        rich_contract = symbol_a
        cheap_contract = symbol_b
        action = f"Short {symbol_a} (Rich) / Long {symbol_b} (Cheap)"
    else:
        rich_contract = symbol_b
        cheap_contract = symbol_a
        action = f"Long {symbol_a} (Cheap) / Short {symbol_b} (Rich)"

    if has_signal:
        status = "opportunity"
        signal_state = "entry"
        message = (
            f"Statistically significant dislocation (|z|={abs(z):.2f} >= {entry_z}). "
            f"{rich_contract} is rich relative to {cheap_contract}. "
            f"Expected edge ({expected_reversion_bps:.1f} bps) survives full round-trip friction ({rt_cost_bps:.1f} bps)."
        )
    elif z_breach and not is_cost_viable:
        status = "friction_trap"
        signal_state = "none"
        message = (
            f"Z-score crossed (|z|={abs(z):.2f}), but spread gap does NOT clear "
            f"estimated round-trip trading friction ({rt_cost_bps:.1f} bps). Edge is negative after costs."
        )
    elif z_breach and roll_risk:
        status = "roll_warning"
        signal_state = "none"
        message = (
            f"Dislocation observed, but one leg is within tender/roll window (<3 days to expiry). "
            f"Holding into delivery violates lifecycle risk limits."
        )
    elif z_breach and not liq_pass:
        status = "liquidity_trap"
        signal_state = "none"
        message = (
            f"Dislocation observed, but thin order book/zero volume prevents executable fill. "
            f"Paper edge will evaporate into execution slippage."
        )
    else:
        status = "neutral"
        signal_state = "none"
        message = "none"

    return {
        "has_signal": has_signal,
        "signal_state": signal_state,
        "pair": f"{symbol_a}/{symbol_b}",
        "symbol_a": symbol_a,
        "symbol_b": symbol_b,
        "status": status,
        "date": str(latest["date"].date()) if hasattr(latest["date"], "date") else str(latest["date"]),
        "z_score": z,
        "spread_bps": spread_bps,
        "spread_rupees": spread_rupees,
        "action": action if has_signal else "none",
        "cheap_contract": cheap_contract if has_signal else None,
        "rich_contract": rich_contract if has_signal else None,
        "estimated_costs_bps": rt_cost_bps,
        "expected_gross_reversion_bps": round(expected_reversion_bps, 2),
        "expected_net_edge_bps": round(net_edge_bps, 2),
        "liquidity_status_a": latest["liquidity_a"],
        "liquidity_status_b": latest["liquidity_b"],
        "volume_a": vol_a,
        "volume_b": vol_b,
        "oi_a": oi_a,
        "oi_b": oi_b,
        "days_to_expiry_a": days_to_exp_a,
        "days_to_expiry_b": days_to_exp_b,
        "checks": {
            "is_gap_unusual": bool(z_breach),
            "is_cost_viable": bool(is_cost_viable),
            "is_liquid": bool(liq_pass),
            "is_expiry_safe": bool(not roll_risk),
        },
        "message": message,
        "evaluated_at": dt.datetime.utcnow().isoformat(),
    }


def get_all_active_signals(
    df: pd.DataFrame,
    window: int = 20,
    cost_per_leg_bps: float = DEFAULT_COST_PER_LEG_BPS,
) -> list[dict[str, Any]]:
    """Scan all key tracked pairs and return current signals."""
    pairs = [
        ("GOLDM", "GOLDTEN"),
        ("GOLDM", "GOLDGUINEA"),
        ("GOLDM", "GOLDPETAL"),
        ("GOLDTEN", "GOLDGUINEA"),
        ("GOLDTEN", "GOLDPETAL"),
        ("GOLDGUINEA", "GOLDPETAL"),
    ]
    signals = []
    for a, b in pairs:
        sig = evaluate_pair_signal(df, a, b, window=window, cost_per_leg_bps=cost_per_leg_bps)
        signals.append(sig)
    return signals
