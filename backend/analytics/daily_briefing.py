"""
KARAT – Daily Briefing Analytics.

Deterministic calculation layer computing day-over-day market metrics from real Bhavcopy data:
1. Price changes per contract (norm_close vs norm_prev_close, in Rs/g and %).
2. Same-expiry gap vs GOLDTEN today vs yesterday (bps change).
3. Contracts 5 days or fewer from expiry.
4. Liquidity changes (volume, grams traded, open interest).
5. Data hygiene warnings (no-trade rows, rejected files, missing weekdays).
6. Deterministic list of facts and strict template-written summary (<= 80 words).

All calculations live strictly in this data layer, never in UI components or AI prompts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


def compute_daily_briefing(
    df: pd.DataFrame,
    quality_report_path: Optional[Path | str] = None,
) -> dict[str, Any]:
    """
    Computes deterministic daily briefing figures comparing the latest trading date
    against the previous trading date in df.
    """
    if df.empty:
        return {
            "data_available": False,
            "message": "Not enough data yet",
        }


    work_df = df.copy()
    work_df.columns = [c.lower() for c in work_df.columns]
    work_df = work_df.loc[:, ~work_df.columns.duplicated()]


    unique_dates = sorted(work_df["date"].astype(str).unique().tolist())
    trading_days_loaded = len(unique_dates)

    if trading_days_loaded < 2:
        return {
            "data_available": False,
            "trading_days_loaded": trading_days_loaded,
            "message": "Not enough data yet. Daily briefing requires at least 2 consecutive trading dates.",
        }

    date_today = unique_dates[-1]
    date_yesterday = unique_dates[-2]

    df_today = work_df[work_df["date"].astype(str).str.startswith(date_today)].copy()
    df_prev = work_df[work_df["date"].astype(str).str.startswith(date_yesterday)].copy()


    price_changes: list[dict[str, Any]] = []
    facts_list: list[str] = []


    goldten_today_by_exp: dict[str, float] = {}
    goldten_prev_by_exp: dict[str, float] = {}

    for _, row in df_today[df_today["symbol"] == "GOLDTEN"].iterrows():
        goldten_today_by_exp[str(row["expiry_date"])] = float(row.get("norm_close", 0.0) or 0.0)

    for _, row in df_prev[df_prev["symbol"] == "GOLDTEN"].iterrows():
        goldten_prev_by_exp[str(row["expiry_date"])] = float(row.get("norm_close", 0.0) or 0.0)

    same_expiry_gaps: list[dict[str, Any]] = []
    near_expiry_contracts: list[dict[str, Any]] = []
    liquidity_summary: dict[str, Any] = {
        "total_volume_today": int(df_today["volume_lots"].sum()) if "volume_lots" in df_today.columns else 0,
        "total_volume_prev": int(df_prev["volume_lots"].sum()) if "volume_lots" in df_prev.columns else 0,
        "total_grams_today": float(df_today["grams_traded"].sum()) if "grams_traded" in df_today.columns else 0.0,
        "total_grams_prev": float(df_prev["grams_traded"].sum()) if "grams_traded" in df_prev.columns else 0.0,
        "total_oi_today": int(df_today["oi_lots"].sum()) if "oi_lots" in df_today.columns else 0,
        "total_oi_prev": int(df_prev["oi_lots"].sum()) if "oi_lots" in df_prev.columns else 0,
    }


    for sym in ["GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"]:
        sym_today = df_today[df_today["symbol"] == sym]
        if sym_today.empty:
            continue


        active_today = sym_today.sort_values("volume_lots", ascending=False).iloc[0]
        exp = str(active_today["expiry_date"])
        norm_close = float(active_today.get("norm_close", 0.0) or 0.0)
        norm_prev_close = float(active_today.get("norm_prev_close", 0.0) or 0.0)


        sym_prev = df_prev[(df_prev["symbol"] == sym) & (df_prev["expiry_date"] == exp)]
        if not sym_prev.empty and norm_prev_close == 0:
            norm_prev_close = float(sym_prev.iloc[0].get("norm_close", 0.0) or 0.0)

        chg_rs = round(norm_close - norm_prev_close, 2)
        pct_chg = round((chg_rs / norm_prev_close * 100.0), 2) if norm_prev_close > 0 else 0.0

        price_changes.append({
            "symbol": sym,
            "expiry_date": exp,
            "norm_close": norm_close,
            "norm_prev_close": norm_prev_close,
            "change_rs_per_g": chg_rs,
            "pct_change": pct_chg,
            "close_raw": float(active_today.get("close", 0.0) or 0.0),
            "prev_close_raw": float(active_today.get("prev_close", 0.0) or 0.0),
        })

        sign = "+" if chg_rs >= 0 else ""
        facts_list.append(f"{sym} ({exp}) moved {sign}₹{chg_rs:g}/g ({sign}{pct_chg:.2f}%) to ₹{norm_close:.2f}/g.")


    for _, row in df_today.iterrows():
        sym = str(row["symbol"])
        exp = str(row["expiry_date"])
        norm_c = float(row.get("norm_close", 0.0) or 0.0)

        if sym != "GOLDTEN" and exp in goldten_today_by_exp:
            g_today = goldten_today_by_exp[exp]
            g_prev = goldten_prev_by_exp.get(exp)

            if g_today > 0 and norm_c > 0:
                gap_today_bps = round(((norm_c - g_today) / g_today) * 10_000.0, 1)


                gap_prev_bps: Optional[float] = None
                gap_chg_bps: Optional[float] = None

                matching_prev = df_prev[(df_prev["symbol"] == sym) & (df_prev["expiry_date"] == exp)]
                if not matching_prev.empty and g_prev and g_prev > 0:
                    norm_prev = float(matching_prev.iloc[0].get("norm_close", 0.0) or 0.0)
                    gap_prev_bps = round(((norm_prev - g_prev) / g_prev) * 10_000.0, 1)
                    gap_chg_bps = round(gap_today_bps - gap_prev_bps, 1)

                same_expiry_gaps.append({
                    "symbol": sym,
                    "expiry_date": exp,
                    "gap_today_bps": gap_today_bps,
                    "gap_prev_bps": gap_prev_bps,
                    "gap_change_bps": gap_chg_bps,
                })

                if gap_chg_bps is not None:
                    chg_sign = "+" if gap_chg_bps >= 0 else ""
                    facts_list.append(
                        f"Same-expiry gap for {sym} ({exp}) vs GOLDTEN shifted {chg_sign}{gap_chg_bps:g} bps to {gap_today_bps:+g} bps."
                    )


    for _, row in df_today.iterrows():
        days = int(row.get("days_to_expiry", 999) or 999)
        if days <= 5:
            near_expiry_contracts.append({
                "symbol": str(row["symbol"]),
                "expiry_date": str(row["expiry_date"]),
                "days_to_expiry": days,
                "volume_lots": int(row.get("volume_lots", 0) or 0),
            })

    if near_expiry_contracts:
        near_desc = ", ".join(f"{c['symbol']} ({c['expiry_date']}: {c['days_to_expiry']}d)" for c in near_expiry_contracts)
        facts_list.append(f"Contracts within 5-day delivery tender window: {near_desc}.")
    else:
        facts_list.append("Zero contracts currently within the 5-day tender window.")


    vol_chg_pct = round(((liquidity_summary["total_volume_today"] - liquidity_summary["total_volume_prev"]) / liquidity_summary["total_volume_prev"]) * 100.0, 1) if liquidity_summary["total_volume_prev"] > 0 else 0.0
    facts_list.append(
        f"Total exchange turnover: {liquidity_summary['total_volume_today']:,} lots ({liquidity_summary['total_grams_today']/1000:,.1f} kg), shifted {vol_chg_pct:+.1f}% vs previous session."
    )


    no_trade_today = df_today[df_today["no_trade"] == True]
    no_trade_count = len(no_trade_today)


    rejected_files_count = 0
    missing_weekdays_count = 0
    missing_weekdays: list[str] = []

    if quality_report_path:
        q_path = Path(quality_report_path)
    else:
        q_path = Path("backend/data/clean/quality_report.json")

    if q_path.exists():
        try:
            with open(q_path, "r", encoding="utf-8") as f:
                q_data = json.load(f)
                raw_rej = q_data.get("files_rejected_count", q_data.get("files_rejected", 0))
                rejected_files_count = len(raw_rej) if isinstance(raw_rej, list) else int(raw_rej or 0)
                cal_reconcil = q_data.get("trading_calendar_reconciliation", {})
                unexplained = cal_reconcil.get("unexplained_missing_trading_days", [])
                missing_weekdays_count = len(unexplained)
        except Exception:
            pass

    warnings_list: list[str] = []
    if no_trade_count > 0:
        warnings_list.append(f"{no_trade_count} contracts recorded zero trading volume today.")
    if missing_weekdays_count > 0:
        warnings_list.append(f"{missing_weekdays_count} unexplained missing trading days detected in data range.")
    if rejected_files_count > 0:
        warnings_list.append(f"{rejected_files_count} raw Bhavcopy files rejected during ingestion.")

    if warnings_list:
        facts_list.append("Data quality notes: " + "; ".join(warnings_list))
    else:
        facts_list.append("Data hygiene: zero no-trade rows; clean date sequence.")


    lead_change = price_changes[0] if price_changes else None
    lead_sym = lead_change["symbol"] if lead_change else "MCX Gold"
    lead_sign = "+" if (lead_change and lead_change["change_rs_per_g"] >= 0) else ""
    lead_settle = f"₹{lead_change['norm_close']:,.2f}/g" if lead_change else "—"
    lead_change_rs = f"{lead_sign}₹{abs(lead_change['change_rs_per_g']):g}/g" if (lead_change and lead_change['change_rs_per_g'] != 0) else "flat"
    lead_pct = f"{lead_sign}{lead_change['pct_change']:.2f}%" if lead_change else "0.0%"

    template_parts = [
        f"On {date_today}, {lead_sym} settled at {lead_settle} ({lead_change_rs}, {lead_pct} change).",
        f"Total gold turnover reached {liquidity_summary['total_grams_today']/1000:,.1f} kg ({liquidity_summary['total_volume_today']:,} lots).",
    ]

    if same_expiry_gaps:
        g = same_expiry_gaps[0]
        g_sign = "+" if (g["gap_change_bps"] or 0) >= 0 else ""
        template_parts.append(f"The {g['symbol']} gap vs GOLDTEN stands at {g['gap_today_bps']:+g} bps ({g_sign}{g.get('gap_change_bps') or 0:g} bps change).")

    if near_expiry_contracts:
        template_parts.append(f"{len(near_expiry_contracts)} contract(s) sit within 5 days of expiry.")
    else:
        template_parts.append("No contracts are within the 5-day delivery tender window.")

    if missing_weekdays_count > 0:
        template_parts.append(f"Audit note: {missing_weekdays_count} weekdays are unpopulated in the sample.")

    template_summary = " ".join(template_parts)


    words = template_summary.split()
    if len(words) > 80:
        template_summary = " ".join(words[:80]) + "."

    return {
        "data_available": True,
        "as_of_date": date_today,
        "previous_date": date_yesterday,
        "trading_days_loaded": trading_days_loaded,
        "provenance_label": f"MCX data, {trading_days_loaded} trading days, as of {date_today}",
        "price_changes": price_changes,
        "same_expiry_gaps": same_expiry_gaps,
        "near_expiry_contracts": near_expiry_contracts,
        "liquidity_summary": liquidity_summary,
        "data_warnings": {
            "no_trade_count": no_trade_count,
            "rejected_files_count": rejected_files_count,
            "missing_weekdays_count": missing_weekdays_count,
            "missing_weekdays": missing_weekdays,
        },
        "facts_list": facts_list,
        "template_summary": template_summary,
        "template_word_count": len(template_summary.split()),
        "summary_label": f"AI-generated summary of computed figures, data as of {date_today}",
    }
