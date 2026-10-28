"""
KARAT – FastAPI Application.

High-performance quantitative commodity derivatives API serving
normalised MCX gold futures, cross-contract spreads, backtesting engines,
term structures, calendar lifecycles, and data quality audits.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
from typing import Any, Dict, List, Optional

from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.config import (
    BUILD_FRACTION,
    CONTRACTS,
    DEFAULT_COST_PER_LEG_BPS,
    ENTRY_Z,
    EXIT_Z,
    PROJECT_ROOT,
    THIN_LIQUIDITY_SLIPPAGE_MULT,
    TIME_STOP_DAYS,
    TRACKED_SYMBOLS,
    ZSCORE_WINDOW,
)
from backend.data.parser import get_data_quality_report, get_data_status, load_data
from backend.analytics.normaliser import (
    get_normalised_snapshot,
    get_sparkline_data,
    normalise_dataframe,
)
from backend.analytics.spread import (
    compute_spread_series,
    get_spread_chart_data,
    get_spread_summary,
)
from backend.backtest.engine import run_backtest
from backend.analytics.signals import evaluate_pair_signal, get_all_active_signals
from backend.analytics.term_structure import get_term_structure, compute_historical_curve_regimes
from backend.calendar.lifecycle import get_contract_calendar, get_upcoming_expiries_and_roll_windows
from backend.api.ai_guide import ChatRequest, ChatResponse, ask_ai_guide


# ==========================================
# PYDANTIC RESPONSE MODELS
# ==========================================

class HealthResponse(BaseModel):
    project: str = "KARAT"
    status: str = "online"
    data_source: str = Field(..., description="'mcx' or 'sample'")
    data_status: str = Field("demo", description="'real' | 'demo' | 'incomplete'")
    last_verified_trading_date: Optional[str] = None
    timestamp: str
    supported_contracts: List[str]


class ContractItem(BaseModel):
    symbol: str
    lot_size_g: float
    quote_base_g: float
    purity: int
    expiry_window: str
    listing_start: Optional[str] = None
    raw_price: Optional[float] = None
    expiry_date: Optional[str] = None
    price_per_gram: Optional[float] = None
    normalised_price: Optional[float] = None
    premium_vs_ref: Optional[float] = None
    premium_bps: Optional[float] = None
    volume: Optional[int] = None
    open_interest: Optional[int] = None
    liquidity_status: str
    daily_change: Optional[float] = None
    daily_change_pct: Optional[float] = None
    sparkline: Optional[List[dict]] = None


class ContractsResponse(BaseModel):
    data_source: str
    data_status: str = "demo"
    last_verified_trading_date: Optional[str] = None
    as_of_date: Optional[str] = None
    reference_symbol: str
    contracts: List[dict]
    available_dates: List[str]


class MethodologyResponse(BaseModel):
    data_source: str = "mcx"
    data_status: str = "demo"
    last_verified_trading_date: Optional[str] = None
    formula: str
    explanation: List[str]
    cost_model: dict
    strategy_rules: dict
    disclaimer: str
    limitations: List[str]


# ==========================================
# APP INITIALIZATION
# ==========================================

app = FastAPI(
    title="KARAT API",
    description="Cross-contract relative-value intelligence for MCX gold futures",
    version="1.0.0",
)

# Enable CORS for frontend local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global dataset cache with reload capability
_DATA_CACHE = None
_DATA_SOURCE = None


def get_cached_data():
    global _DATA_CACHE, _DATA_SOURCE
    if _DATA_CACHE is None:
        _DATA_CACHE, _DATA_SOURCE = load_data()
    return _DATA_CACHE, _DATA_SOURCE


@app.get("/health", response_model=HealthResponse)
@app.get("/api/health", response_model=HealthResponse)
def read_root():
    df, source = get_cached_data()
    status, last_verified = get_data_status(df, source)
    return {
        "project": "KARAT",
        "status": "online",
        "data_source": source,
        "data_status": status,
        "last_verified_trading_date": last_verified,
        "timestamp": dt.datetime.utcnow().isoformat(),
        "supported_contracts": TRACKED_SYMBOLS,
    }


# ==========================================
# 1. CONTRACTS & MARKET SUMMARY
# ==========================================
@app.get("/contracts", response_model=ContractsResponse)
@app.get("/api/contracts", response_model=ContractsResponse)
def get_contracts(
    date: Optional[str] = Query(None, description="ISO Date YYYY-MM-DD"),
    reference: str = Query("GOLDTEN", description="Reference contract symbol"),
):
    df, source = get_cached_data()
    parsed_date = None
    if date:
        try:
            parsed_date = dt.date.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")

    status, last_verified = get_data_status(df, source, date=parsed_date)
    snapshot = get_normalised_snapshot(df, date=parsed_date, reference_symbol=reference)

    for item in snapshot:
        sym = item["symbol"]
        item["sparkline"] = get_sparkline_data(df, sym, days=25)

    all_dates = sorted(df["Date"].unique())
    latest_date_str = str(all_dates[-1].date()) if all_dates and hasattr(all_dates[-1], "date") else str(all_dates[-1]) if all_dates else None

    return {
        "data_source": source,
        "data_status": status,
        "last_verified_trading_date": last_verified,
        "as_of_date": str(parsed_date) if parsed_date else latest_date_str,
        "reference_symbol": reference,
        "contracts": snapshot,
        "available_dates": [
            str(d.date()) if hasattr(d, "date") else str(d)
            for d in all_dates[-60:]
        ],
    }


# ==========================================
# 2. SPREAD LAB & ANALYTICS
# ==========================================
@app.get("/spread")
@app.get("/api/spread")
def get_spread(
    pair: Optional[str] = Query(None, description="e.g. GOLDM-GOLDTEN or GOLDM/GOLDTEN"),
    symbol_a: Optional[str] = Query(None),
    symbol_b: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    window: int = Query(ZSCORE_WINDOW),
    cost_per_leg_bps: float = Query(DEFAULT_COST_PER_LEG_BPS),
):
    # Resolve pair symbols
    sym_a = "GOLDM"
    sym_b = "GOLDTEN"
    if pair:
        parts = pair.replace("/", "-").split("-")
        if len(parts) == 2:
            sym_a, sym_b = parts[0].strip(), parts[1].strip()
    else:
        if symbol_a: sym_a = symbol_a.strip()
        if symbol_b: sym_b = symbol_b.strip()

    df, source = get_cached_data()
    status, last_verified = get_data_status(df, source)
    summary = get_spread_summary(df, sym_a, sym_b, window, cost_per_leg_bps)
    chart_data = get_spread_chart_data(df, sym_a, sym_b, window)

    # Optional date filtering
    if from_date:
        chart_data = [pt for pt in chart_data if pt["date"] >= from_date]
    if to_date:
        chart_data = [pt for pt in chart_data if pt["date"] <= to_date]

    # Pre-generate 3D Terrain mesh data for the pair
    terrain_points = []
    for idx, pt in enumerate(chart_data[-40:]):
        terrain_points.append({
            "idx": idx,
            "date": pt["date"],
            "z": pt["z_score"],
            "spread_bps": pt["spread_bps"],
            "is_breach": abs(pt["z_score"]) >= ENTRY_Z,
        })

    return {
        "data_source": source,
        "data_status": status,
        "last_verified_trading_date": last_verified,
        "pair": f"{sym_a}/{sym_b}",
        "summary": summary,
        "chart": chart_data,
        "terrain_points": terrain_points,
    }


# ==========================================
# 3. SIGNALS & ALERTS
# ==========================================
@app.get("/signal")
@app.get("/api/signal")
def get_signal(
    date: Optional[str] = Query(None, description="As-of date YYYY-MM-DD"),
    pair: Optional[str] = Query(None, description="e.g. GOLDM-GOLDTEN"),
    symbol_a: str = Query("GOLDM"),
    symbol_b: str = Query("GOLDTEN"),
    window: int = Query(ZSCORE_WINDOW),
    cost_per_leg_bps: float = Query(DEFAULT_COST_PER_LEG_BPS),
):
    if pair:
        parts = pair.replace("/", "-").split("-")
        if len(parts) == 2:
            symbol_a, symbol_b = parts[0].strip(), parts[1].strip()

    df, source = get_cached_data()
    status, last_verified = get_data_status(df, source, date=date)
    if date:
        df_filtered = df[df["Date"] <= pd.Timestamp(date)]
        if df_filtered.empty:
            df_filtered = df
    else:
        df_filtered = df

    pair_signal = evaluate_pair_signal(
        df_filtered, symbol_a, symbol_b, window=window, cost_per_leg_bps=cost_per_leg_bps
    )
    all_signals = get_all_active_signals(
        df_filtered, window=window, cost_per_leg_bps=cost_per_leg_bps
    )

    # Quiet output rule: if no qualifying signal, explicitly set signal="none"
    signal_output = pair_signal["action"] if pair_signal.get("has_signal") else "none"

    return {
        "data_source": source,
        "data_status": status,
        "last_verified_trading_date": last_verified,
        "signal": signal_output,
        "state": pair_signal.get("signal_state", "none"),
        "current_pair_signal": pair_signal,
        "all_active_signals": all_signals,
    }


# ==========================================
# 4. STRATEGY BACKTESTING
# ==========================================
@app.get("/backtest")
@app.get("/api/backtest")
def get_backtest(
    period: str = Query("unseen", description="'build' or 'unseen' or 'all'"),
    symbol_a: str = Query("GOLDM"),
    symbol_b: str = Query("GOLDTEN"),
    window: int = Query(ZSCORE_WINDOW),
    entry_z: float = Query(ENTRY_Z),
    exit_z: float = Query(EXIT_Z),
    time_stop_days: int = Query(TIME_STOP_DAYS),
    cost_bps: Optional[float] = Query(None, description="Alternative alias for cost_per_leg_bps"),
    cost_per_leg_bps: float = Query(DEFAULT_COST_PER_LEG_BPS),
    slippage_x: Optional[float] = Query(None, description="Alternative alias for slippage_mult"),
    slippage_mult: float = Query(THIN_LIQUIDITY_SLIPPAGE_MULT),
    build_fraction: float = Query(BUILD_FRACTION),
):
    if cost_bps is not None:
        cost_per_leg_bps = cost_bps
    if slippage_x is not None:
        slippage_mult = slippage_x

    df, source = get_cached_data()
    status, last_verified = get_data_status(df, source)
    results = run_backtest(
        df,
        symbol_a=symbol_a,
        symbol_b=symbol_b,
        window=window,
        entry_z=entry_z,
        exit_z=exit_z,
        time_stop_days=time_stop_days,
        cost_per_leg_bps=cost_per_leg_bps,
        slippage_mult=slippage_mult,
        build_fraction=build_fraction,
    )
    if not results.get("data_available", True):
        from backend.data.parser import load_sample
        try:
            sample_df = load_sample()
            demo_results = run_backtest(
                sample_df,
                symbol_a=symbol_a,
                symbol_b=symbol_b,
                window=window,
                entry_z=entry_z,
                exit_z=exit_z,
                time_stop_days=time_stop_days,
                cost_per_leg_bps=cost_per_leg_bps,
                slippage_mult=slippage_mult,
                build_fraction=build_fraction,
            )
            demo_results["data_source"] = "sample"
            demo_results["data_status"] = "demo"
            demo_results["last_verified_trading_date"] = last_verified
            demo_results["selected_period"] = period
            demo_results["notice"] = "Needs about 100 trading days of real data"
            demo_results["verdict"]["headline_conclusion"] = (
                "Walk-forward backtesting requires extended multi-cycle real data for statistically confident round-trips. "
                "Demo simulation shown below for execution workflow validation."
            )
            return demo_results
        except Exception:
            pass

    results["data_source"] = source
    results["data_status"] = status
    results["last_verified_trading_date"] = last_verified
    results["selected_period"] = period
    return results


# ==========================================
# 5. TERM STRUCTURE
# ==========================================
@app.get("/curve")
@app.get("/api/curve")
def get_curve(
    symbol: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
):
    df, source = get_cached_data()
    parsed_date = None
    if date:
        try:
            parsed_date = dt.date.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")

    status, last_verified = get_data_status(df, source, date=parsed_date)
    curve_data = get_term_structure(df, date=parsed_date, symbol=symbol)
    curve_data["data_source"] = source
    curve_data["data_status"] = status
    curve_data["last_verified_trading_date"] = last_verified
    return curve_data


@app.get("/curve/regimes")
@app.get("/api/curve/regimes")
def get_curve_regimes(
    symbol: Optional[str] = Query("GOLDM"),
):
    df, source = get_cached_data()
    status, last_verified = get_data_status(df, source)
    regimes = compute_historical_curve_regimes(df, symbol=symbol or "GOLDM")
    return {
        "symbol": symbol or "GOLDM",
        "data_source": source,
        "data_status": status,
        "last_verified_trading_date": last_verified,
        "regimes": regimes,
        "total_observations": len(regimes),
    }


# ==========================================
# 6. CONTRACT CALENDAR
# ==========================================
@app.get("/calendar")
@app.get("/api/calendar")
def get_calendar():
    df, source = get_cached_data()
    status, last_verified = get_data_status(df, source)
    cal = get_contract_calendar(df)
    upcoming = get_upcoming_expiries_and_roll_windows(df)
    cal["upcoming_roll_windows"] = upcoming
    cal["data_source"] = source
    cal["data_status"] = status
    cal["last_verified_trading_date"] = last_verified
    cal["contracts"] = [
        {
            "symbol": sym,
            "lot_size_g": cfg.lot_size_g,
            "quote_base_g": cfg.quote_base_g,
            "purity": cfg.purity,
            "expiry_window": cfg.expiry_window,
            "listing_start": cfg.listing_start or "Established",
        }
        for sym, cfg in CONTRACTS.items()
    ]
    cal["active_cycles"] = [
        {
            "symbol": u["symbol"],
            "expiry_date": u["expiry_date"],
            "days_to_expiry": max(0, u.get("days_to_expiry", 0)),
            "roll_window_start": u.get("roll_window_start", "N/A"),
            "roll_window_end": u.get("roll_window_end", "N/A"),
            "tender_period_start": u.get("tender_start", "N/A"),
            "last_trade_date": u.get("last_trading_day", "N/A"),
        }
        for u in upcoming
    ]
    return cal


# ==========================================
# 7. DATA QUALITY & REJECTION AUDIT
# ==========================================
@app.get("/quality")
@app.get("/api/quality")
def get_quality():
    df, source = get_cached_data()
    return get_data_quality_report(df, source)


# ==========================================
# 8. CSV & DATA EXPORTS
# ==========================================
@app.get("/export/trades.csv")
@app.get("/api/export/trades.csv")
def export_trades_csv(
    symbol_a: str = Query("GOLDM"),
    symbol_b: str = Query("GOLDTEN"),
    cost_per_leg_bps: float = Query(DEFAULT_COST_PER_LEG_BPS),
    cost_bps: Optional[float] = Query(None),
    period: str = Query("all", description="Period to export: 'unseen', 'build', or 'all'"),
):
    if cost_bps is not None:
        cost_per_leg_bps = cost_bps

    df, _ = get_cached_data()
    bt = run_backtest(df, symbol_a=symbol_a, symbol_b=symbol_b, cost_per_leg_bps=cost_per_leg_bps)
    if not bt.get("data_available", True):
        from backend.data.parser import load_sample
        try:
            sample_df = load_sample()
            bt = run_backtest(sample_df, symbol_a=symbol_a, symbol_b=symbol_b, cost_per_leg_bps=cost_per_leg_bps)
        except Exception:
            pass

    req_period = (period or "all").lower().strip()
    if req_period == "build":
        trades = bt.get("build", {}).get("trades", [])
    elif req_period == "unseen":
        trades = bt.get("unseen", {}).get("trades", [])
    else:
        trades = bt.get("combined", {}).get("trades", [])
        if not trades:
            trades = bt.get("unseen", {}).get("trades", []) + bt.get("build", {}).get("trades", [])

    output = io.StringIO()
    fieldnames = [
        "entry_date", "exit_date", "direction", "symbol_a", "symbol_b",
        "lots_a", "lots_b", "grams_a", "grams_b",
        "entry_spread_bps", "exit_spread_bps", "entry_z", "exit_z",
        "gross_pnl_bps", "gross_pnl_rs", "cost_rs", "net_pnl_rs",
        "pnl_leg_a_rs", "pnl_leg_b_rs", "turnover_rs",
        "holding_days", "exit_reason",
        "thin_entry", "thin_exit", "expiry_a", "expiry_b",
        "raw_a_entry", "raw_b_entry", "raw_a_exit", "raw_b_exit"
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for t in trades:
        writer.writerow(t)

    filename = f"karat_{symbol_a}_{symbol_b}_{req_period}_trades.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/export/signals.csv")
@app.get("/api/export/signals.csv")
def export_signals_csv():
    df, _ = get_cached_data()
    try:
        signals = get_all_active_signals(df)
    except Exception:
        from backend.data.parser import load_sample
        sample_df = load_sample()
        signals = get_all_active_signals(sample_df)

    output = io.StringIO()
    fieldnames = [
        "pair", "symbol_a", "symbol_b", "has_signal", "direction", "z_score", "spread_bps",
        "expected_net_edge_bps", "breakeven_bps", "liquidity_status", "days_to_expiry_a", "days_to_expiry_b", "reason"
    ]
    if signals:
        all_keys = list(signals[0].keys())
        for k in fieldnames:
            if k not in all_keys:
                all_keys.append(k)
        writer = csv.DictWriter(output, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        for s in signals:
            writer.writerow(s)
    else:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=karat_active_signals.csv"},
    )


@app.get("/export/normalised.csv")
@app.get("/api/export/normalised.csv")
def export_normalised_csv():
    df, _ = get_cached_data()
    try:
        norm_df = normalise_dataframe(df)
    except Exception:
        from backend.data.parser import load_sample
        norm_df = normalise_dataframe(load_sample())
    output = io.StringIO()
    norm_df.to_csv(output, index=False)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=karat_normalised_gold_prices.csv"},
    )


@app.get("/export/spreads.csv")
@app.get("/api/export/spreads.csv")
def export_spreads_csv(
    pair: str = Query("GOLDM_GOLDTEN", description="Contract pair, e.g. GOLDM_GOLDTEN"),
):
    df, _ = get_cached_data()
    parts = pair.split("_")
    symbol_a = parts[0] if len(parts) > 0 else "GOLDM"
    symbol_b = parts[1] if len(parts) > 1 else "GOLDTEN"
    try:
        spread_df = compute_spread_series(df, symbol_a=symbol_a, symbol_b=symbol_b)
    except Exception:
        from backend.data.parser import load_sample
        spread_df = compute_spread_series(load_sample(), symbol_a=symbol_a, symbol_b=symbol_b)

    output = io.StringIO()
    spread_df.to_csv(output, index=False)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=karat_{symbol_a}_{symbol_b}_spreads.csv"},
    )


@app.get("/export/clean.csv")
@app.get("/api/export/clean.csv")
def export_clean_csv():
    df, _ = get_cached_data()
    output = io.StringIO()
    df.to_csv(output, index=False)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=karat_clean_bhavcopy.csv"},
    )


@app.get("/export/quality.json")
@app.get("/api/export/quality.json")
def export_quality_json():
    qr_path = PROJECT_ROOT / "quality_report.json"
    if qr_path.exists():
        content = qr_path.read_text(encoding="utf-8")
    else:
        df, source = get_cached_data()
        content = json.dumps(get_data_quality_report(df, source), indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=karat_quality_report.json"},
    )


# ==========================================
# 9. METHODOLOGY & LIMITATIONS
# ==========================================
@app.get("/methodology", response_model=MethodologyResponse)
@app.get("/api/methodology", response_model=MethodologyResponse)
def get_methodology():
    df, source = get_cached_data()
    status, last_verified = get_data_status(df, source)
    return {
        "data_source": source,
        "data_status": status,
        "last_verified_trading_date": last_verified,
        "formula": "Normalized Price = (Raw Price / Quote Base in grams) * (999 / Purity)",
        "explanation": [
            "MCX quotes GOLDM in ₹ per 10g at 995 fineness, whereas GOLDTEN is 10g at 999 fineness.",
            "KARAT scales all contracts to a standard 1 gram of 999 fineness gold.",
            "GOLDM is mathematically scaled by (999 / 995) ≈ 1.00402.",
        ],
        "cost_model": {
            "base_cost_per_leg_bps": DEFAULT_COST_PER_LEG_BPS,
            "total_legs_per_round_trip": 4,
            "slippage_multiplier_on_thin_liquidity": 2.0,
            "rationale": "Relative-value trading requires simultaneously establishing 2 legs and closing 2 legs = 4 order fills. Realistic transaction costs must deduct brokerage, STT/CTT, exchange turnover charges, SEBI fees, GST, and bid-ask slippage.",
        },
        "strategy_rules": {
            "entry_z": ENTRY_Z,
            "exit_z": EXIT_Z,
            "time_stop_days": TIME_STOP_DAYS,
            "lookback_window": ZSCORE_WINDOW,
            "out_of_sample_split": "60% Build (In-Sample) / 40% Unseen (Out-of-Sample)",
        },
        "disclaimer": (
            "Settlement prices are not executable fill prices. "
            "Volume is not market depth. "
            "Historical results do not guarantee future performance. "
            "This application is for analytical and educational research, not investment advice."
        ),
        "limitations": [
            "Settlement prices are official end-of-day values, not executable fills.",
            "Volume is not market depth; the liquidity score is a proxy.",
            "GOLDTEN history is short (listed from 2025 onwards).",
            "Carry effects between expiries are approximated based on calendar days.",
            "Results depend on the chosen lookback window.",
            "Sample data is bundled for offline operation and clearly labeled.",
            "Nothing here is investment advice.",
        ],
    }


# ==========================================
# 8. KARAT AI GUIDE ENDPOINT
# ==========================================
@app.post("/chat", response_model=ChatResponse)
@app.post("/api/chat", response_model=ChatResponse)
async def chat_with_ai(request: ChatRequest):
    """
    Intelligent quantitative AI Guide endpoint.
    Provides context-aware, numbers-backed explanations of MCX gold spreads,
    normalisation, z-scores, transaction frictions, backtesting, and delivery rules.
    """
    return await ask_ai_guide(request)


# ==========================================
# 9. POSITION MATCHER & CONTRACT CHOOSER
# ==========================================
from backend.analytics.position_matcher import compute_position_matcher
from backend.analytics.daily_briefing import compute_daily_briefing
from backend.analytics.guardrails import get_prewritten_explanation, validate_ai_output


@app.get("/position-matcher")
@app.get("/api/position-matcher")
def get_position_matcher(
    quantity_g: float = Query(100.0, description="Target gold quantity in grams"),
    target_expiry: Optional[str] = Query(None, description="Optional target expiry date (YYYY-MM-DD)"),
    as_of_date: Optional[str] = Query(None, description="Optional calculation date (YYYY-MM-DD)"),
):
    df, _ = get_cached_data()
    return compute_position_matcher(
        df=df,
        quantity_g=quantity_g,
        target_expiry=target_expiry,
        as_of_date=as_of_date,
    )


# ==========================================
# 10. DAILY BRIEFING
# ==========================================
@app.get("/daily-briefing")
@app.get("/api/daily-briefing")
def get_daily_briefing():
    df, _ = get_cached_data()
    return compute_daily_briefing(df=df)


# ==========================================
# 11. EXPLAIN THIS PANEL (WITH GUARDRAILS)
# ==========================================
class ExplainPanelRequest(BaseModel):
    panel_id: str
    panel_title: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    as_of_date: Optional[str] = None

ExplainPanelRequest.model_rebuild()


@app.post("/explain-panel")
@app.post("/api/explain-panel")
async def explain_panel(req: ExplainPanelRequest):
    """
    Generates or retrieves deterministic plain-language explanations for a panel
    with strict numbers validation guardrails.
    """
    template_exp = get_prewritten_explanation(req.panel_id, req.data)
    as_of = req.as_of_date or "2026-10-14"

    return {
        "panel_id": req.panel_id,
        "panel_title": req.panel_title or template_exp["title"],
        "explanation": f"{template_exp['body']}\n\n{template_exp['caveat']}",
        "body": template_exp["body"],
        "caveat": template_exp["caveat"],
        "source": "template_guardrails",
        "provenance_label": f"AI-generated explanation, based on data as of {as_of}",
        "raw_numbers_used": req.data or {},
    }


# ==========================================
# 12. STATIC FRONTEND MOUNT
# ==========================================
STATIC_DIR = Path(__file__).resolve().parent.parent.parent


@app.get("/", response_class=FileResponse)
def serve_root():
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


