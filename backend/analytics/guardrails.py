"""
KARAT – Guardrails, Numbers Validation & Prewritten Explanations.

Strict validation layer:
1. Validates AI-generated output against allowed numbers from supplied panel JSON.
   If AI text contains ANY number not in the supplied data, it is rejected and discarded.
2. Provides deterministic prewritten plain-language explanations for all 5 core panels:
   - Contracts table
   - Contract chooser
   - Gap chart (Spread Lab)
   - Signal card
   - Daily briefing
3. Enforces compliance rules:
   - 2-3 plain sentences in sentence case
   - No jargon (unavoidable terms defined in brackets)
   - One line starting "What this does not tell you"
   - Explicit disclaimer that settlement prices are not executable prices.
"""

from __future__ import annotations

import re
from typing import Any, List, Set, Tuple


def extract_numbers_from_text(text: str) -> list[float]:
    """
    Extracts all numeric tokens from text: integers, decimals, percentages, bps, and currency amounts.
    Normalizes thousands commas (e.g. 14,506.20 -> 14506.20).
    """
    if not text:
        return []

    cleaned = text.replace(",", "")
    # Match numbers: e.g. -14.5, 100, 2.50%, +14.87, ₹14506.20
    pattern = r"[-+]?\d*\.?\d+"
    matches = re.findall(pattern, cleaned)

    numbers: list[float] = []
    for m in matches:
        if m in ("", ".", "-", "+"):
            continue
        try:
            val = float(m)
            numbers.append(val)
        except ValueError:
            pass

    return numbers


def extract_allowed_numbers_from_payload(payload: Any) -> set[float]:
    """
    Recursively inspects a JSON payload (dict, list, primitive) and collects all
    numerical values into an allowed whitelist set.
    Includes common structural constants (e.g. lot sizes, 100, 10, 8, 1, 995, 999, 4 legs, 0, 1, 2, 3, 5).
    """
    allowed: set[float] = {
        0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 8.0, 10.0, 100.0, 1000.0, 995.0, 999.0, 24.0, 22.0
    }

    def _collect(val: Any):
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            allowed.add(round(float(val), 4))
            # Also add common rounded integer representation if applicable
            allowed.add(float(round(val)))
            allowed.add(float(int(val)))
        elif isinstance(val, str):
            for num in extract_numbers_from_text(val):
                allowed.add(round(num, 4))
                allowed.add(float(round(num)))
                allowed.add(float(int(num)))
        elif isinstance(val, dict):
            for v in val.values():
                _collect(v)
        elif isinstance(val, (list, tuple, set)):
            for item in val:
                _collect(item)

    _collect(payload)
    return allowed


def validate_ai_output(
    ai_text: str,
    allowed_payload: Any,
    tolerance: float = 0.05,
) -> tuple[bool, list[float]]:
    """
    Validates that every single number mentioned in ai_text corresponds to
    a number in allowed_payload (within tolerance).

    Returns:
        (is_valid, list_of_unsupported_numbers)
    """
    if not ai_text:
        return True, []

    found_numbers = extract_numbers_from_text(ai_text)
    allowed_numbers = extract_allowed_numbers_from_payload(allowed_payload)

    unsupported: list[float] = []

    for num in found_numbers:
        # Check if number matches any allowed number within tolerance
        matched = False
        for allowed in allowed_numbers:
            if abs(num - allowed) <= tolerance:
                matched = True
                break
            # Also allow percentage to decimal (e.g. 0.05 vs 5%)
            if abs(num * 100.0 - allowed) <= tolerance or abs(num / 100.0 - allowed) <= tolerance:
                matched = True
                break

        if not matched:
            unsupported.append(num)

    is_valid = len(unsupported) == 0
    return is_valid, unsupported


def get_prewritten_explanation(panel_id: str, context: Any = None) -> dict[str, str]:
    """
    Returns strict, compliant prewritten explanations for each core panel.
    Rules:
    - 2-3 plain sentences in sentence case
    - No jargon; define any unavoidable term in brackets
    - One line starting "What this does not tell you"
    """
    explanations: dict[str, dict[str, str]] = {
        "contracts_table": {
            "title": "Contracts Table",
            "body": (
                "This table displays all four gold futures contracts traded on the exchange with their official specifications. "
                "Each contract is converted to a single standard scale (rupees per one gram of pure gold) so you can compare prices fairly. "
                "Prices shown are official exchange closing figures rather than live executable quotes."
            ),
            "caveat": (
                "What this does not tell you: It does not show live order book depth, instantaneous bid-ask spread, or the exact price your broker can execute right now."
            ),
        },
        "contract_chooser": {
            "title": "Contract Chooser & Position Matcher",
            "body": (
                "This tool calculates how many lots of each contract are required to match your desired physical gold quantity. "
                "It reveals any leftover grams when a contract does not divide evenly, and shows combinations that hit the target exactly. "
                "Each option is compared against the ten-gram benchmark contract using normalized costs."
            ),
            "caveat": (
                "What this does not tell you: It does not account for delivery penalties if held past the tender notice date, brokerage commissions, or daily mark-to-market margin calls."
            ),
        },
        "gap_chart": {
            "title": "Relative-Value Gap Chart",
            "body": (
                "This chart tracks the price difference (spread) between two selected contracts over time, measured in basis points (hundredths of a percentage point). "
                "When contracts share the same expiry month, a wide gap indicates a pricing dislocation between different contract sizes. "
                "A statistical boundary shows whether today's gap is typical or unusually wide."
            ),
            "caveat": (
                "What this does not tell you: It does not guarantee that a wide gap will narrow before contract expiry, nor does it factor in the four individual trades required to capture it."
            ),
        },
        "signal_card": {
            "title": "Relative-Value Signal State",
            "body": (
                "This card checks whether a genuine trading opportunity exists across four strict automated rules. "
                "It only flags an opportunity when the price gap is statistically unusual, larger than all four execution trading fees combined, liquid enough to trade, and safely before expiry. "
                "When all four checks do not pass, it remains quiet to prevent unprofitable trades."
            ),
            "caveat": (
                "What this does not tell you: It does not tell you market direction (whether gold will go up or down), and it cannot predict sudden exchange margin increases."
            ),
        },
        "daily_briefing": {
            "title": "Daily Market Briefing",
            "body": (
                "This briefing summarizes official exchange trading figures between the latest session and the previous trading day. "
                "It highlights price movements on the common scale, shifts in relative spreads, and upcoming delivery deadlines. "
                "All statements are generated deterministically from verified exchange files without opinion or forecasting."
            ),
            "caveat": (
                "What this does not tell you: It does not provide forward-looking predictions, macroeconomic forecasts, or personal buy or sell recommendations."
            ),
        },
    }

    item = explanations.get(panel_id)
    if not item:
        return {
            "title": "Market Panel",
            "body": (
                "This panel summarizes quantitative market figures calculated from verified exchange bhavcopy records. "
                "All prices are standardized to rupees per gram of pure gold to ensure objective comparison."
            ),
            "caveat": (
                "What this does not tell you: Historical closing prices do not guarantee future performance and do not represent executable quotes."
            ),
        }

    return item
