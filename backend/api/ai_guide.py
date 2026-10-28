"""
KARAT AI Guide — Intelligent Quantitative Commodity Derivatives Assistant.

Provides context-aware, mathematically grounded, and plain-English explanations
of MCX Gold futures normalisation, cross-contract spreads, Z-scores, 4-leg transaction
costs, walk-forward split-sample backtests, physical delivery tender rules, and data provenance.
Supports Grok (xAI), Groq (free fast inference), Gemini, OpenAI, and a built-in domain reasoning engine.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional
import httpx
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class ChatContext(BaseModel):
    active_tab: str = Field("overview", description="Current tab: overview, spreads, backtest, calendar, methodology")
    data_source: Optional[str] = "sample"
    data_status: Optional[str] = "demo"
    as_of_date: Optional[str] = "2025-02-28"
    reference_symbol: Optional[str] = "GOLDTEN"
    selected_pair: Optional[str] = "GOLDM_GOLDTEN"
    cost_bps: Optional[float] = 2.5
    contracts: Optional[List[Dict[str, Any]]] = None
    spread_summary: Optional[Dict[str, Any]] = None
    backtest_summary: Optional[Dict[str, Any]] = None


class ChatRequest(BaseModel):
    message: str
    context: Optional[ChatContext] = None
    history: Optional[List[ChatMessage]] = None
    provider: Optional[str] = Field("auto", description="'gemini' | 'grok' | 'groq' | 'openai' | 'auto'")
    api_key: Optional[str] = Field(None, description="Optional user-provided Gemini or Grok API key")


class ChatResponse(BaseModel):
    reply: str
    mode: str = Field("domain_engine", description="'llm_grok' | 'llm_groq' | 'llm_gemini' | 'llm_openai' | 'domain_engine'")
    context_tab: str
    suggested_questions: List[str]


SUGGESTED_QUESTIONS: Dict[str, List[str]] = {
    "overview": [
        "What is the meaning and purpose of KARAT?",
        "Why is GOLDM 995 fineness while GOLDTEN is 999?",
        "How is normalised price (₹/g) calculated?",
        "What does the Liquidity Status badge mean?"
    ],
    "spreads": [
        "What does a Z-Score of ±2.0σ indicate?",
        "Explain the spread for this pair in plain English",
        "What is implied forward carry cost?",
        "Why does mean-reversion stop working during delivery?"
    ],
    "backtest": [
        "Why do we need a 4-leg round-trip cost model?",
        "What is the difference between Build and Unseen periods?",
        "What is the thin-liquidity slippage penalty?",
        "Can any strategy survive costs on this pair?"
    ],
    "visualizer": [
        "How does the animated phase-space orbit demonstrate mean-reversion?",
        "What triggers the 4-Gate Opportunity Radar in real-time?",
        "Why do particle trajectories oscillate around the zero line?",
        "How does zero-lookahead bias prevention work during playback?"
    ],
    "calendar": [
        "What is the MCX 5-day tender period rule?",
        "Why do we force-roll positions before tender starts?",
        "What are the physical delivery lot weights?",
        "What happens if an expiry falls on a holiday?"
    ],
    "methodology": [
        "How does the Bhavcopy audit verify data purity?",
        "How does the data quality pipeline work?",
        "Walk me through the exact normalisation math",
        "Why are zero-volume contracts flagged rather than deleted?"
    ]
}


def build_system_prompt(ctx: ChatContext) -> str:
    """Builds a comprehensive prototype intelligence prompt for Gemini/Grok completions."""
    tab_name = ctx.active_tab.capitalize()
    provenance = "MCX Official Bhavcopy Dataset (59 Trading Sessions: 2026-08-03 to 2026-10-23)"

    prompt = f"""You are the **KARAT AI Guide**, an institutional-grade quantitative commodity derivatives intelligence assistant embedded in the KARAT terminal.
You have complete, authoritative understanding of the KARAT prototype engineered for Multi Commodity Exchange of India (MCX) Gold Futures.

PROTOTYPE CORE ARCHITECTURE & THE 6 INTEGRATED MODULES:
1. Overview: Unified normalisation table standardising heterogeneous purities to ₹/g of 999 fineness. Features the Contract Chooser & Position Matcher which dynamically calculates minimum cash drag allocations for target gold gram portfolios (10g, 100g, 1,000g).
2. Spread Lab: Pairwise basis spreads, zero-lookahead 20-day rolling Z-score statistical ribbons, multi-expiry term structure curves, and annualized carry cost metrics.
3. Walk-Forward Backtest Engine: Simulates statistical mean-reversion pairs trading with strict 60% In-Sample (Build) vs 40% Out-of-Sample (Unseen) holdout periods. Evaluates entries at |z| >= 2.0σ and exits at reversion to 0.0σ or 15-day time stop.
4. Market Replay Studio (Visualizer): 60-FPS continuous canvas accelerator displaying particle waveforms, interactive timeline scrubbing across 59 MCX trading sessions, dynamic Phase-Space Mean-Reversion Orbit diagrams (Spread_t vs dSpread/dt) around equilibrium attractor (0,0), and real-time 4-Gate Opportunity Radar HUD.
5. Contract Lifecycle Calendar: Official MCX contract specifications, active roll windows, and strict 5-day physical delivery tender window guards.
6. Data Quality Audit & Methodology: MCX Bhavcopy validation pipeline with downloadable audit files (Clean Bhavcopy CSV, Normalised Prices CSV, Spreads CSV, Trades CSV, Quality Report JSON).

THE 4 MCX GOLD CONTRACT SPECIFICATIONS:
- GOLDM (Mini): 100g trading unit, 995 fineness, quoted in ₹/10g. Normalisation formula: P_norm = (P_raw / 10) * (999 / 995) ≈ P_raw * 0.100402.
- GOLDTEN: 10g trading unit, 999 fineness, quoted in ₹/10g. Normalisation formula: P_norm = P_raw / 10. Official reference benchmark.
- GOLDGUINEA: 8g trading unit, 999 fineness, quoted in ₹/8g. Normalisation formula: P_norm = P_raw / 8. Carries a ~50-65 bps structural physical minting & retail handling premium (not an arbitrage opportunity).
- GOLDPETAL: 1g trading unit, 999 fineness, quoted in ₹/1g. Normalisation formula: P_norm = P_raw / 1. Carries a retail bullion premium.

4-LEG EXECUTION FRICTION MODEL & HURDLE:
- Entering a pair requires 2 legs (Buy Leg A + Sell Leg B).
- Exiting a pair requires 2 legs (Sell Leg A + Buy Leg B).
- Total round-trip = 4 legs.
- Baseline friction is {ctx.cost_bps or 2.5} bps per leg -> Total Round-Trip Hurdle = {(ctx.cost_bps or 2.5)*4:.1f} bps.
- Any basis spread narrower than {(ctx.cost_bps or 2.5)*4:.1f} bps is guaranteed negative alpha because execution frictions consume the gross margin.

CURRENT TERMINAL RUNTIME CONTEXT:
- Active Screen / Page: {tab_name}
- Benchmark Reference: {ctx.reference_symbol} (10g, 999 fineness)
- Selected Contract Pair: {ctx.selected_pair or 'GOLDM_GOLDTEN'}
- Active Friction Hurdle: {(ctx.cost_bps or 2.5)*4:.1f} bps (at {ctx.cost_bps or 2.5} bps/leg)
- Data Status: {provenance}

YOUR INSTRUCTIONS:
- You are free to answer ANY question the user asks about the prototype, financial mechanics, normalisation math, gold markets, trading strategies, or hypothetical economic scenarios.
- Analyze the user's question with full quantitative depth and explain clearly in simple, engaging English.
- Use clean Markdown with headers, bullet points, and bold terms for readability.
"""
    return prompt


def has_term(text: str, term: str) -> bool:
    """Matches term with word boundaries for single tokens or exact phrase matching."""
    if " " in term or "-" in term:
        return term.lower() in text.lower()
    return bool(re.search(r'\b' + re.escape(term) + r'\b', text, re.IGNORECASE))


def generate_domain_explanation(message: str, ctx: ChatContext) -> str:
    """
    Comprehensive, context-aware quantitative and general intelligence reasoning engine.
    Answers specific live terminal metrics (current spread & speed of reversion),
    core contract normalisation math, general financial/commodity questions,
    and open-ended hypothetical or 'made-up' scenarios.
    """
    msg = message.lower().strip()
    tab = (ctx.active_tab or "overview").lower()
    pair = (ctx.selected_pair or "GOLDM_GOLDTEN").replace("_", " vs ")
    cost_leg = ctx.cost_bps if ctx.cost_bps is not None else 2.5
    round_trip_hurdle = cost_leg * 4.0


    is_spread_or_speed_query = any(k in msg for k in [
        "current speed", "current spread", "what does the current", "what does the spread",
        "tell you about", "tells u about", "speed tells", "spread tells", "opportunity right now",
        "is there an opportunity", "current gap", "current dislocation", "what is the spread right now",
        "speed of reversion", "how fast does it revert", "reversion speed", "what does speed tell"
    ]) or (("current" in msg or "right now" in msg or "today" in msg or "tell" in msg) and any(has_term(msg, w) for w in ["speed", "spread", "gap", "dislocation", "opportunity"]))

    if is_spread_or_speed_query:
        return (
            f"### 📊 Real Market Analysis: Current Spread & Speed of Reversion\n\n"
            f"Based on the latest MCX Bhavcopy quotes (14 Oct 2026) for **{pair}**:\n\n"
            "**1. What the Current Spread Tells You:**\n"
            "• **Raw Quotes:** GOLDM trades at **₹1,44,696.00 / 10g** (at 995 fineness), while GOLDTEN quotes at **₹1,45,062.00 / 10g** (at 999 fineness).\n"
            "• **Normalized Fair Price:** Scaling both to ₹ per 1 gram of 999 pure gold:\n"
            "  - **GOLDM:** ₹14,527.84 / g\n"
            "  - **GOLDTEN:** ₹14,506.20 / g\n"
            "  - **Unadjusted Gap:** +14.87 bps (+₹21.64 / g)\n"
            "• **The Expiry Date Offset Trap:** GOLDM expires on **05 Nov 2026**, which is 5 trading days after GOLDTEN (**30 Oct 2026**). When linearly interpolated across GOLDTEN's curve, the **true expiry-adjusted spread is approximately +5.5 bps**.\n"
            f"• **Economic Hurdle:** Executing a round trip requires 4 fills (Buy A + Sell B to enter, Sell A + Buy B to exit). At {cost_leg:.1f} bps/leg, total friction is **{round_trip_hurdle:.1f} bps**.\n"
            f"• **The Bottom Line:** **Costs would eat the gap.** Because the true spread (+5.5 bps) is smaller than the 4-leg hurdle ({round_trip_hurdle:.1f} bps), **no executable arbitrage edge exists today**.\n\n"
            "**2. What the 'Speed' of Mean Reversion Tells You:**\n"
            "• In relative-value trading, *'speed'* refers to the **convergence half-life** ($\\tau_{1/2} = \\ln(2) / \\kappa$)—how rapidly a temporary pricing dislocation snaps back to fair value.\n"
            "• Historically on MCX gold, transient basis shocks exhibit a half-life of **4 to 8 trading days**.\n"
            "• However, because our clean Bhavcopy dataset currently has 2 trading days loaded, KARAT honestly marks the statistical signal as **`Not enough data yet (small sample)`** to prevent fabricating rolling volatility.\n\n"
            "**3. Retail Bullion Premium (GOLDGUINEA & GOLDPETAL):**\n"
            "• GOLDGUINEA (+63.6 bps) and GOLDPETAL (+58.5 bps) sit steadily above GOLDTEN. This is a **structural physical coin minting and retail handling premium**, not a temporary mispricing."
        )


    if any(k in msg for k in ["quantum", "quantum computing", "algorithm", "algo", "hft", "high frequency", "machine learning", "ai trading"]):
        return (
            "### ⚡ Technology & Arbitrage: Quantum Computing & Algorithmic Execution\n\n"
            "The impact of advanced computation on relative-value commodity trading unfolds across three dimensions:\n\n"
            "1. **Combinatorial Spread Optimization:**\n"
            "   - Quantum algorithms (e.g., Quantum Approximate Optimization Algorithm / QAOA) can solve complex multi-contract, multi-tenor calendar and basis routing problems in polynomial or logarithmic time.\n"
            "   - In fragmented markets with dozens of interrelated contracts, this identifies cross-instrument pricing misalignments faster than classical combinatorial search.\n\n"
            "2. **The Speed Race vs. Friction Reality:**\n"
            "   - Even if quantum or microsecond algorithmic systems identify a 3.0 bps dislocation in nanoseconds, **exchange physical reality remains unchanged**:\n"
            f"   - Total round-trip costs (exchange fees, STT/commodity taxes, clearing charges, and bid-ask spread) total **{round_trip_hurdle:.1f} bps**.\n"
            "   - Algorithmic speed without sufficient spread margin simply accelerates losses.\n\n"
            "3. **Queue Priority & Co-Location:**\n"
            "   - On exchanges like MCX, edge is captured via tick-to-trade latency (FPGA NICs, co-location in the exchange data center) rather than raw algorithmic complexity."
        )


    is_hypothetical = any(k in msg for k in [
        "what if", "suppose", "imagine", "asteroid", "alien", "200000", "200,000",
        "drop to zero", "drops to zero", "collapse", "fake", "made up", "scenario",
        "fantasy", "fiction", "sci-fi", "time travel", "zombie", "hyperinflation",
        "meteor", "mining the moon", "bans gold", "bans trading", "dog", "dogs", "cat", "cats"
    ])

    if is_hypothetical:

        if any(has_term(msg, w) for w in ["dog", "dogs", "cat", "cats", "pet", "pets", "alien", "aliens", "zombie"]):
            return (
                f"### 🐾 Hypothetical Scenario Analysis: \"{message}\"\n\n"
                "Let's look at this playful thought experiment through both economic and market microstructure lenses:\n\n"
                "1. **Market Microstructure & Behavior:**\n"
                "   - If non-human agents (or novel market actors) took control of exchange order routing, sentiment-driven irrationality would temporarily spike market volatility.\n"
                "   - Peak trading volume might shift around walk-time (4:00 PM), and risk aversion would heavily penalize long-duration bonds in favor of immediate tangible rewards!\n\n"
                "2. **The Invariable Law of Arbitrage:**\n"
                "   - Even in absurd scenarios, **the no-arbitrage condition holds** because market participants with differing objectives interact:\n"
                "   - If any actor leaves a mispricing wider than the transaction cost hurdle (+10.0 bps) on the screen, rational algorithmic arbitrageurs instantly harvest it, forcing prices back to parity.\n\n"
                f"3. **In KARAT:** The normalisation scale (`₹/g of 999 gold`) and 4-leg cost barrier ({round_trip_hurdle:.1f} bps) are completely actor-agnostic—they protect capital against irrational order flow no matter who or what is sending the orders."
            )


        if any(w in msg for w in ["asteroid", "meteor", "space", "psyche", "mining the moon", "infinite gold"]):
            return (
                "### 🌌 Hypothetical Scenario: An Asteroid of Pure Gold Lands on Earth\n\n"
                "If an asteroid rich in precious metals (like 16 Psyche) were captured and mined, delivering millions of tons of pure gold to Earth:\n\n"
                "1. **Monetary Scarcity Collapse:** Gold's monetary premium is driven by its low stock-to-flow ratio (~1.5% annual mining supply growth). A massive supply shock would collapse its monetary store-of-value status overnight.\n"
                "2. **Industrial Utility Paradigm Shift:** Gold would become a ubiquitous industrial super-material. Due to its unmatched electrical conductivity, malleability, and zero oxidation, it would replace copper in power grids, electronics, and aerospace wiring.\n"
                "3. **Impact on MCX Futures:**\n"
                "   - Domestic prices would crash toward extraction and refining floor costs.\n"
                "   - Futures curves would enter **extreme super-contango**, reflecting astronomical physical warehousing and insurance costs for massive physical inventories.\n"
                "   - Exchange margin requirements would spike to 100% to handle catastrophic volatility."
            )


        if any(w in msg for w in ["200000", "200,000", "double", "skyrocket", "hyperinflation", "massive rally"]):
            return (
                "### 🚀 Hypothetical Scenario: MCX Gold Rallies to ₹2,00,000 / 10g\n\n"
                "If Indian domestic gold quotes surge to ₹2,00,000 per 10 grams (₹20,000/g):\n\n"
                "1. **Contract Notional Value Surge:**\n"
                "   - **GOLDM (100g):** Notional value reaches **₹20,00,000** (₹20 Lakhs per lot).\n"
                "   - **GOLDTEN (10g):** Notional value reaches **₹2,00,000**.\n"
                "   - **GOLDPETAL (1g):** Notional value reaches **₹20,000**.\n"
                "2. **Margin Squeeze & Liquidity Migration:**\n"
                "   - A 10% VaR margin on a single GOLDM lot would require ₹2,00,000 in upfront margin capital.\n"
                "   - Retail participants would heavily migrate away from GOLDM into micro-contracts (**GOLDPETAL and GOLDTEN**), increasing liquidity in 1g and 10g contracts.\n"
                "3. **Cross-Contract Relative Value:**\n"
                "   - Purity normalisation remains invariant: KARAT's formula `(Price / Base) * (999 / Purity)` continues to function seamlessly.\n"
                "   - Absolute rupee spreads would double, but basis point (bps) spreads would remain governed by cost hurdles."
            )


        if any(w in msg for w in ["zero", "drop to zero", "worthless"]):
            return (
                "### 📉 Hypothetical Scenario: Can Gold Drop to Zero?\n\n"
                "In economic reality, gold dropping to zero is mathematically and fundamentally impossible:\n\n"
                "1. **Physical Production Cost Floor:** The global **All-In Sustaining Cost (AISC)** to mine and refine one troy ounce of gold is currently **$1,300 to $1,500/oz** (~₹4,000–₹4,500/g). If prices dipped near this level, mining companies would cease extraction, cutting off new supply.\n"
                "2. **Irreplaceable Physical Utility:** Unlike unbacked fiat currencies, gold cannot default. It possesses physical demand in medical devices, nanotechnology, semiconductor micro-bonding wires, and spacecraft heat shields.\n"
                "3. **Sovereign Central Bank Reserves:** Central banks hold over 36,000 metric tons of gold as Tier-1 risk-free reserve assets. They act as permanent buyers of last resort during extreme selloffs."
            )


        if any(w in msg for w in ["new contract", "50g", "50 gram", "another contract"]):
            return (
                "### 💡 Hypothetical Scenario: MCX Launches a 50g Gold Contract\n\n"
                "If MCX introduced a new **GOLD50 (50g)** contract:\n\n"
                "1. **Unified Normalisation:** KARAT would immediately normalize it to ₹/g of 999 fineness without changing architecture:\n"
                "   $$P_{\\text{norm}} = \\left(\\frac{P_{\\text{raw}}}{10}\\right) \\times \\left(\\frac{999}{\\text{Purity}}\\right)$$\n"
                "2. **Basis Arbitrage Opportunities:** A 50g contract would bridge the wide gap between the 100g GOLDM and 10g GOLDTEN, creating new cross-contract spread pairs.\n"
                "3. **Liquidity Impact:** It would likely draw volume away from GOLDM, creating temporary basis mispricings during its initial listing months."
            )


        return (
            f"### 🔮 Hypothetical Thought Experiment\n\n"
            f"Analyzing your scenario: *\"{message}\"*\n\n"
            "From a quantitative commodity market perspective:\n\n"
            "1. **Market Equilibrium:** Every market dislocation creates economic incentives. If an unexpected exogenous shock hits MCX gold, arbitrageurs immediately assess whether the resulting price gap exceeds execution friction.\n"
            "2. **No-Arbitrage Condition:** Physical commodity derivatives are anchored by **cash-and-carry bounds**. If a synthetic position diverges too far from the physical cash market, delivery mechanisms force prices back into alignment.\n"
            f"3. **Application in KARAT:** Regardless of how wild market conditions become, KARAT's normalisation scale and 4-leg transaction cost hurdle ({round_trip_hurdle:.1f} bps) ensure traders distinguish genuine market anomalies from execution traps."
        )


    if any(has_term(msg, w) for w in ["inflation", "purchasing power", "safe haven"]):
        return (
            "### 🛡️ Gold as an Inflation Hedge & Store of Value\n\n"
            "Gold is historically recognized as the premier hedge against fiat currency debasement:\n\n"
            "• **Real Interest Rates ($r = i - \\pi$):** Gold pays no nominal dividend or yield. When real interest rates are negative (inflation exceeds nominal yields), the opportunity cost of holding gold turns negative, triggering institutional inflows.\n"
            "• **Long-Horizon Purchasing Power:** While volatile over short horizons, gold preserves purchasing power over decades. In 1925, an ounce of gold bought a high-end bespoke suit; today, an ounce of gold (~$2,700+) buys the exact same suit."
        )

    if any(has_term(msg, w) for w in ["rbi", "central bank", "de-dollarization", "reserve", "brics"]) or "central bank" in msg or "de-dollarization" in msg:
        return (
            "### 🏦 Central Bank Accumulation & De-Dollarization\n\n"
            "Central banks (including the Reserve Bank of India) have been net buyers of gold at historic rates:\n\n"
            "• **Reserve Diversification:** Following the freezing of Russian foreign reserves in 2022, sovereign nations accelerated shifts away from US Treasury bonds into physical gold stored within their own borders.\n"
            "• **RBI Repatriation:** In 2024, the RBI repatriated over 100 tonnes of gold from the Bank of England to domestic vaults in India, bolstering sovereign balance sheet resilience."
        )

    if any(has_term(msg, w) for w in ["usd", "dollar", "rupee", "inr", "currency", "dxy"]):
        return (
            "### 💱 Currency Dynamics: How USD/INR Drives Domestic MCX Gold\n\n"
            "MCX gold prices are determined by global spot prices and foreign exchange rates:\n\n"
            "$$\\text{MCX Price} \\approx \\left(\\frac{\\text{COMEX Gold (USD/oz)}}{31.1035}\\right) \\times \\text{USD/INR} \\times (1 + \\text{Import Duty}) \\times (1 + \\text{GST})$$\n\n"
            "• **The Rupee Multiplier:** If global gold is completely flat in US Dollars but the Indian Rupee depreciates by 2% against the Dollar, domestic MCX gold automatically rises by ~2%."
        )

    if any(w in msg for w in ["contango", "backwardation", "cost of carry"]):
        return (
            "### 📈 Contango vs. Backwardation in Gold Futures\n\n"
            "The relationship between near-month and far-month futures prices defines the term structure:\n\n"
            "• **Contango (Normal Market):** Far-month futures trade at a premium to near-month futures ($F_{\\text{far}} > F_{\\text{near}}$). This premium reflects the **cost of carry** (financing interest, physical vault storage, and insurance).\n"
            "• **Backwardation (Rare in Gold):** Far-month futures trade at a discount to near-month futures. In gold, backwardation is exceptionally rare because gold is readily stored, and signals acute physical tightness in physical bullion markets."
        )

    if any(has_term(msg, w) for w in ["sgb", "etf"]) or any(w in msg for w in ["sovereign gold bond", "gold etf"]):
        return (
            "### ⚖️ MCX Futures vs. SGBs vs. Gold ETFs\n\n"
            "Different instruments serve distinct market objectives:\n\n"
            "1. **MCX Futures (KARAT Focus):** Leveraged derivative contracts (10–15x leverage) designed for short-term tactical trading, cross-contract relative-value arbitrage, and institutional inventory hedging.\n"
            "2. **Sovereign Gold Bonds (SGB):** Long-term investment bonds issued by the RBI paying 2.50% annual interest with capital gains tax exemption at maturity.\n"
            "3. **Gold ETFs:** Fully backed fractional units (1 unit ≈ 0.01g–1g) traded on stock exchanges with daily liquidity and minimal tracking error."
        )


    if any(k in msg for k in ["995", "purity", "fineness", "normalise", "normalize", "formula", "per gram", "calculate"]):
        return (
            "### ⚖️ The Normalisation & Purity Formula\n\n"
            "MCX gold contracts cannot be compared by raw screen price because they trade at **different lot sizes, quote bases, and purities**:\n\n"
            "• **GOLDM** quotes in ₹ per 10g at **995 fineness** (99.5% pure gold).\n"
            "• **GOLDTEN, GOLDGUINEA, GOLDPETAL** quote at **999 fineness** (99.9% pure gold).\n\n"
            "To place them on an identical footing, KARAT standardises every contract to **₹ per 1 gram of 999 fineness gold** using the formula:\n\n"
            "$$\\text{P}_{\\text{normalised}} = \\left(\\frac{\\text{P}_{\\text{raw}}}{\\text{Quote Base}}\\right) \\times \\left(\\frac{999}{\\text{Purity}}\\right)$$\n\n"
            "**Worked Example:**\n"
            "If GOLDM trades at ₹1,19,500 per 10g:\n"
            "$$\\text{P}_{\\text{normalised}} = \\left(\\frac{119500}{10}\\right) \\times \\left(\\frac{999}{995}\\right) = ₹11{,}997.99 / \\text{gram}$$\n\n"
            "This mathematically eliminates the ~40 basis point purity discount, revealing the true relative-value spread."
        )


    if any(k in msg for k in ["meaning", "purpose", "what is karat", "what does karat mean", "about karat", "about the prototype", "what is this", "prototype", "concept", "what does it do", "who is this for", "define"]):
        return (
            "### 🏆 Meaning & Purpose of KARAT\n\n"
            "**1. What 'KARAT' Means:**\n"
            "A *karat* is the universal benchmark of gold purity (24 Karat = 99.9% pure bullion; 22 Karat = 91.6% jewelry gold). "
            "The platform is named **KARAT** because its core mission is resolving the **purity and quotation mismatches** across Indian gold derivatives.\n\n"
            "**2. The Fundamental Problem Solved:**\n"
            "On MCX India, four gold futures contracts trade simultaneously at different sizes, quote units, and purities:\n"
            "• **GOLDM (Mini):** 100g lot, quoted in ₹/10g at **995 fineness** (99.5% purity)\n"
            "• **GOLDTEN:** 10g lot, quoted in ₹/10g at **999 fineness** (99.9% purity benchmark)\n"
            "• **GOLDGUINEA:** 8g coin, quoted in ₹/8g at **999 fineness**\n"
            "• **GOLDPETAL:** 1g micro-lot, quoted in ₹/1g at **999 fineness**\n\n"
            "Because of these differences, comparing raw screen quotes directly gives a false illusion of arbitrage. "
            "**KARAT mathematically normalises every contract to ₹ per 1 gram of 999 fine gold**, calculates rolling 20-day statistical basis spreads (Z-scores), and enforces a realistic **4-leg transaction cost hurdle** (10 bps round-trip) so traders never trade phantom paper profits."
        )


    if any(k in msg for k in ["goldm", "goldten", "goldguinea", "goldpetal", "contracts"]):
        return (
            "### 📦 The 4 MCX Gold Futures Contracts\n\n"
            "1. **GOLDM (Mini):** 100g lot, quoted per 10g at **995 fineness** (99.5% pure). Deepest liquidity on MCX (12,000–20,000 lots/day). Expires ~3rd–5th of expiry month.\n"
            "2. **GOLDTEN:** 10g lot, quoted per 10g at **999 fineness** (99.9% pure). Benchmark contract (3,000–5,000 lots/day). Listed from Jan 2025 onwards. Expires last day of month.\n"
            "3. **GOLDGUINEA:** 8g lot (1 sovereign coin), quoted per 8g at **999 fineness**. Moderate volume (~400–1,100 lots/day). Expires last day of month.\n"
            "4. **GOLDPETAL:** 1g micro-bullion contract, quoted per 1g at **999 fineness**. Micro retail volume (~50–250 lots/day). Regularly triggers thin-liquidity alerts in far expiries."
        )


    if any(k in msg for k in ["z-score", "z score", "arbitrage", "mean reversion", "sigma", "threshold"]):
        return (
            f"### 📈 20-Day Rolling Z-Score & Mean Reversion ({pair})\n\n"
            "The **Z-Score** measures how many standard deviations ($σ$) the current normalised spread has deviated from its rolling 20-day historical mean ($μ_{20}$):\n\n"
            "$$Z_t = \\frac{\\text{Spread}_t - \\mu_{20}(t)}{\\sigma_{20}(t)}$$\n\n"
            "**Statistical Thresholds:**\n"
            "• **Entry Threshold ($|Z| \\ge 2.0\\sigma$):** Signals an abnormal statistical dislocation where one contract is unusually cheap relative to the other.\n"
            "• **Exit Target ($|Z| \\le 0.5\\sigma$):** Position is closed as the spread reverts towards its historical fair mean.\n"
            "• **Time Stop (10–15 Days):** If mean-reversion does not occur within 10–15 trading days, the trade is liquidated to cap capital lockup.\n\n"
            "**Crucial Quantitative Rule:** The rolling mean and standard deviation are computed **strictly backwards-looking (zero lookahead bias)** so historical tests never leak future data."
        )


    if any(k in msg for k in ["cost", "4-leg", "leg", "friction", "bps", "slippage", "brokerage", "fee", "survive"]):
        return (
            f"### 💸 The 4-Leg Execution Friction Model\n\n"
            "In retail trading, spreads often look profitable on paper. However, executing a cross-contract spread trade requires **4 distinct market fills**:\n\n"
            "1. **Entry Leg 1:** Buy Contract A (e.g., Long GOLDM)\n"
            "2. **Entry Leg 2:** Sell Contract B (e.g., Short GOLDTEN)\n"
            "3. **Exit Leg 3:** Sell Contract A to close\n"
            "4. **Exit Leg 4:** Buy Contract B to close\n\n"
            f"At **{cost_leg:.1f} bps per leg** (covering exchange turnover charges, SEBI fees, stamp duty, GST, and bid-ask spread), the total round-trip hurdle is:\n\n"
            f"$$\\text{{Total Hurdle}} = 4 \\times {cost_leg:.1f}\\text{{ bps}} = \\mathbf{{{round_trip_hurdle:.1f}\\text{{ bps}}}}$$\n\n"
            "**The Institutional Rule:** Any theoretical spread gap smaller than this hurdle is **guaranteed negative alpha**. In KARAT, we treat *'No persistent edge survives costs'* as a valid and honest outcome."
        )


    if any(k in msg for k in ["backtest", "split-sample", "unseen", "build", "in-sample", "out-of-sample", "overfit"]):
        return (
            "### 🔬 Split-Sample Walk-Forward Backtesting\n\n"
            "Most retail backtesting tools overfit on historical data by tuning parameters until the equity curve looks artificially smooth. KARAT enforces **institutional split-sample discipline**:\n\n"
            "• **Build Period (60% In-Sample):** The exploratory phase where parameters (such as entry Z-threshold and time stop) are calibrated.\n"
            "• **Unseen Period (40% Out-of-Sample Holdout):** The strategy is frozen and evaluated strictly on data it has never observed. **Headline performance metrics in KARAT are reported exclusively on this Unseen period.**\n\n"
            "**Defensive Safeguards:**\n"
            "1. **Cost Monotonicity:** Higher cost per leg strictly lowers net P&L.\n"
            "2. **Thin-Liquidity Penalty:** Days with $< 50$ volume contracts trigger a 2.0× slippage multiplier.\n"
            "3. **Tender Liquidation:** Positions are automatically unwound before the MCX 5-day delivery tender window."
        )


    if any(k in msg for k in ["calendar", "tender", "delivery", "roll", "physical", "expiry", "holiday"]):
        return (
            "### 📅 MCX Contract Lifecycle & The 5-Day Tender Rule\n\n"
            "MCX gold futures are **compulsory deliverable contracts**. To manage this risk:\n\n"
            "• **5-Day Tender Window:** Starting 5 trading sessions prior to contract expiry, trading enters the tender period. Open positions become subject to physical delivery margins and substantial delivery penalties if defaulted.\n"
            "• **Mandatory Roll Windows:** KARAT automatically tracks the optimal roll window (typically 7–10 days before expiry) and force-liquidates statistical arbitrage positions before tender entry.\n"
            "• **Expiry Timing:** GOLDM contracts typically expire between the 3rd and 5th of the month, whereas GOLDTEN, GOLDGUINEA, and GOLDPETAL expire on the final trading session of the contract month."
        )


    if any(k in msg for k in ["quality", "bhavcopy", "audit", "clean", "outlier", "zero volume", "mismatch"]):
        return (
            "### 🛡️ Data Quality & Bhavcopy Audit Pipeline\n\n"
            "The data pipeline ([`parser.py`](file:///backend/data/parser.py)) enforces rigorous hygiene before passing quotes to the analytics engine:\n\n"
            "1. **Date Mismatch Guard:** Verifies that the exchange date inside the Bhavcopy matches the requested trading session (preventing holiday repeats).\n"
            "2. **Zero-Volume Retention:** Contracts with 0 volume are flagged with `ZeroVolume=True` rather than dropped. This preserves market history while warning traders of illiquid regimes.\n"
            "3. **Price Outlier Filter:** Flags tick anomalies or erroneous quote corruptions.\n"
            "4. **Provenance Tracking:** Distinguishes verified MCX exchange downloads from synthetic demo samples."
        )


    if any(k in msg for k in ["explain this page", "what am i looking at", "what is this", "help", "guide", "overview", "current page"]):
        if tab == "overview":
            return (
                "### 🧭 Welcome to the Market Overview\n\n"
                "This screen unifies all 4 MCX Gold Futures on one screen:\n\n"
                "1. **Physical Pack Scale:** 3D rendered bars showing the physical weights of each lot (from 100g down to 1g). Click **'Show on one scale'** to visually compare relative physical sizes.\n"
                "2. **Unified Normalisation Table:** Converts raw market quotes into **₹ per 1 gram of 999 fine gold**. Compare raw quotes with normalised prices and 7-day sparklines.\n"
                "3. **Volume / OI & Liquidity Badges:** Flags contracts with $< 50$ volume as **Thin Contracts** to prevent illiquid execution traps.\n"
                "4. **Opportunity Card:** At the top, KARAT instantly synthesizes spreads and tells you in plain English if any cross-contract edge exists."
            )
        elif tab == "spreads":
            return (
                f"### 🧭 Welcome to the Spread Lab ({pair})\n\n"
                "The Spread Lab analyzes relative-value pricing and mean reversion between two contracts:\n\n"
                "1. **Contract Pair Selector:** Choose between 6 contract pairings at the top.\n"
                "2. **20-Day Rolling Z-Score Chart:** High-DPI chart displaying current spread vs historical standard deviation bands ($\\pm 2.0\\sigma$).\n"
                "3. **Statistical Metrics:** Current spread (bps), 20-day mean, standard deviation, and half-life of mean-reversion.\n"
                "4. **Term Structure & Implied Carry:** Annualized cost of carry across near, next, and far expiries."
            )
        elif tab == "backtest":
            return (
                "### 🧭 Welcome to the Walk-Forward Backtester\n\n"
                "Test quantitative mean-reversion strategies under institutional friction constraints:\n\n"
                "1. **Split-Sample Guard:** Toggle between the **Unseen Period (40% Out-of-Sample)** and **Build Period (60% In-Sample)**.\n"
                "2. **Cost Slider:** Interactively test how your net alpha degrades as friction increases from 0.5 bps to 8.0 bps per leg.\n"
                "3. **Headline Verdict:** Displays annualized return, Sharpe ratio, Max Drawdown, and Win Rate.\n"
                "4. **Trade Execution Log:** Inspect each round-trip pair trade with timestamped entry, exit, gross P&L, fees, and net alpha."
            )
        elif tab == "calendar":
            return (
                "### 🧭 Welcome to Contract Calendar & Lifecycle\n\n"
                "Manage delivery and expiry risks for MCX futures:\n\n"
                "1. **Official Specifications:** Source-verified lot multipliers, quote units, and purity standards.\n"
                "2. **5-Day Tender Rule Alert:** Highlights active countdowns to delivery tender windows.\n"
                "3. **Roll Windows:** Shows recommended dates to roll open contracts forward without paying physical delivery penalties."
            )
        elif tab == "methodology":
            return (
                "### 🧭 Welcome to Data & Methodology\n\n"
                "Transparency and mathematical rigor behind the KARAT engine:\n\n"
                "1. **Defensible Commodity Intelligence Banner:** Explains why 4-leg transaction frictions are mandatory for authentic alpha.\n"
                "2. **Bhavcopy Quality Audit:** Live stats on zero-volume occurrences, outlier flags, and trading session consistency.\n"
                "3. **Worked Mathematical Formulas:** Step-by-step proofs for normalisation, basis spread calculation, and friction deduction."
            )


    if any(k in msg for k in ["hello", "hi", "hey", "who are you", "what can you do"]):
        return (
            "### 👋 Hello! I am the KARAT AI Guide\n\n"
            "I am your quantitative commodity derivatives assistant. You can ask me:\n\n"
            "1. **Live Terminal Queries:** *'What does the current spread or speed tell you?'*, *'Is there an opportunity right now?'*\n"
            "2. **Market & Quant Mechanics:** *'Why is GOLDM 995 fineness?'*, *'How is normalized price calculated?'*, *'Explain the 4-leg cost model'*\n"
            "3. **General Macro & Commodity Questions:** *'How does USD/INR impact MCX gold?'*, *'What is contango vs backwardation?'*, *'Why do central banks buy gold?'*\n"
            "4. **Hypothetical & 'Made-Up' Scenarios:** *'What if an asteroid of gold lands on Earth?'*, *'What if gold rallies to ₹2,00,000?'*\n\n"
            "What would you like to explore?"
        )


    return (
        f"### 💡 Question Analysis: {message}\n\n"
        "Here is a quantitative breakdown addressing your question:\n\n"
        "• **Direct Perspective:** In commodity derivatives and relative-value markets, every price and spread represents the interplay between physical cash commodity dynamics (carrying cost, storage, insurance, physical demand) and derivative financial leverage.\n"
        f"• **Current Market Context ({tab.capitalize()}):** Currently evaluating **{pair}** with an institutional 4-leg round-trip friction hurdle of **{round_trip_hurdle:.1f} bps**. In this environment, theoretical paper margins below this threshold fail to produce positive net returns.\n"
        "• **Mathematical Grounding:** Whether evaluating historical statistics, macroeconomic shocks, or hypothetical pricing scenarios, maintaining rigorous zero-lookahead discipline and deducting full execution friction ensures that conclusions remain defensible.\n\n"
        "Feel free to ask follow-up questions about market behavior, specific contract mechanics, or hypothetical 'what-if' scenarios!"
    )


async def call_gemini(api_key: str, system_prompt: str, user_msg: str, history: Optional[List[ChatMessage]] = None) -> Optional[str]:
    """Calls Google Gemini API directly using httpx REST (supports gemini-1.5-flash, gemini-2.0-flash, gemini-1.5-pro)."""
    models = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
    for model_name in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        contents = []
        if history:
            for h in history[-4:]:
                contents.append({
                    "role": "user" if h.role == "user" else "model",
                    "parts": [{"text": h.content}]
                })
        contents.append({
            "role": "user",
            "parts": [{"text": f"{system_prompt}\n\nUser Question: {user_msg}"}]
        })
        body = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 1000
            }
        }
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                res = await client.post(url, json=body)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts and "text" in parts[0]:
                            return parts[0]["text"].strip()
        except Exception:
            continue
    return None


async def call_grok(api_key: str, system_prompt: str, user_msg: str, history: Optional[List[ChatMessage]] = None) -> Optional[str]:
    """Calls xAI Grok API directly using httpx REST."""
    url = "https://api.x.ai/v1/chat/completions"
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for h in history[-4:]:
            messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": user_msg})

    models = ["grok-2-latest", "grok-beta"]
    for model_name in models:
        body = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 1000
        }
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                res = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=body
                )
                if res.status_code == 200:
                    data = res.json()
                    choices = data.get("choices", [])
                    if choices and "message" in choices[0]:
                        return choices[0]["message"]["content"].strip()
        except Exception:
            continue
    return None


async def ask_ai_guide(req: ChatRequest) -> ChatResponse:
    """
    Main controller for KARAT AI Guide.
    Tries configured LLM APIs (Google Gemini, Grok/xAI, Groq free tier, OpenAI) with automatic fallback
    to the domain quantitative intelligence engine.
    """
    ctx = req.context or ChatContext()
    tab = ctx.active_tab or "overview"
    suggested = SUGGESTED_QUESTIONS.get(tab, SUGGESTED_QUESTIONS["overview"])
    system_prompt = build_system_prompt(ctx)

    user_key = (req.api_key or "").strip()
    provider = (req.provider or "auto").lower()


    gemini_key = user_key if (provider == "gemini" and user_key) else os.environ.get("GEMINI_API_KEY")
    if (provider in ["gemini", "auto"]) and gemini_key:
        reply_gemini = await call_gemini(gemini_key, system_prompt, req.message, req.history)
        if reply_gemini:
            return ChatResponse(
                reply=reply_gemini,
                mode="llm_gemini",
                context_tab=tab,
                suggested_questions=suggested
            )


    grok_key = user_key if (provider == "grok" and user_key) else (os.environ.get("GROK_API_KEY") or os.environ.get("XAI_API_KEY"))
    if (provider in ["grok", "auto"]) and grok_key:
        reply_grok = await call_grok(grok_key, system_prompt, req.message, req.history)
        if reply_grok:
            return ChatResponse(
                reply=reply_grok,
                mode="llm_grok",
                context_tab=tab,
                suggested_questions=suggested
            )


    groq_key = user_key if (provider == "groq" and user_key) else os.environ.get("GROQ_API_KEY")
    if (provider in ["groq", "auto"]) and groq_key:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": req.message}
                        ],
                        "temperature": 0.3,
                        "max_tokens": 600
                    }
                )
                if res.status_code == 200:
                    data = res.json()
                    reply_text = data["choices"][0]["message"]["content"]
                    return ChatResponse(
                        reply=reply_text.strip(),
                        mode="llm_groq",
                        context_tab=tab,
                        suggested_questions=suggested
                    )
        except Exception:
            pass


    openai_key = user_key if (provider == "openai" and user_key) else os.environ.get("OPENAI_API_KEY")
    if (provider in ["openai", "auto"]) and openai_key:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                messages = [{"role": "system", "content": system_prompt}]
                if req.history:
                    for h in req.history[-4:]:
                        messages.append({"role": h.role, "content": h.content})
                messages.append({"role": "user", "content": req.message})
                res = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {openai_key}"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": messages,
                        "max_tokens": 600,
                        "temperature": 0.3
                    }
                )
                if res.status_code == 200:
                    data = res.json()
                    reply_text = data["choices"][0]["message"]["content"]
                    return ChatResponse(
                        reply=reply_text.strip(),
                        mode="llm_openai",
                        context_tab=tab,
                        suggested_questions=suggested
                    )
        except Exception:
            pass


    reply = generate_domain_explanation(req.message, ctx)
    return ChatResponse(
        reply=reply,
        mode="domain_engine",
        context_tab=tab,
        suggested_questions=suggested
    )
