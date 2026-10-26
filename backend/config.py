"""
KARAT – contract configuration.

This module is the SINGLE SOURCE OF TRUTH for MCX gold contract specifications.
All values are editable; change them here and the entire pipeline respects them.

Reference: MCX official contract specification page
https://www.mcxindia.com/market-data/gold-contract-specifications
Last verified: 2026-10-20
"""

from dataclasses import dataclass, field
from typing import Dict

# ──────────────────────────────────────────────────────────────────────
# Contract specification
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ContractSpec:
    """Immutable specification for one MCX gold product."""
    symbol: str
    lot_size_g: float          # grams per lot
    quote_base_g: float        # price is quoted per this many grams
    purity: int                # fineness (995 or 999)
    expiry_window: str         # human-readable expiry window description
    listing_start: str | None  # YYYY-MM-DD; None means "available historically"
    notes: str = ""


CONTRACTS: Dict[str, ContractSpec] = {
    "GOLDM": ContractSpec(
        symbol="GOLDM",
        lot_size_g=100,
        quote_base_g=10,
        purity=995,
        expiry_window="3rd–5th of expiry month",
        listing_start=None,
        notes="Main gold futures contract.",
    ),
    "GOLDTEN": ContractSpec(
        symbol="GOLDTEN",
        lot_size_g=10,
        quote_base_g=10,
        purity=999,
        expiry_window="27th–31st of expiry month",
        listing_start="2025-01-01",       # approximate; adjust if MCX differs
        notes="",
    ),
    "GOLDGUINEA": ContractSpec(
        symbol="GOLDGUINEA",
        lot_size_g=8,
        quote_base_g=8,
        purity=999,
        expiry_window="27th–31st of expiry month",
        listing_start=None,
    ),
    "GOLDPETAL": ContractSpec(
        symbol="GOLDPETAL",
        lot_size_g=1,
        quote_base_g=1,
        purity=999,
        expiry_window="27th–31st of expiry month",
        listing_start=None,
    ),
}

# Symbols we track (order matters for display / default pairing)
TRACKED_SYMBOLS = list(CONTRACTS.keys())

# ──────────────────────────────────────────────────────────────────────
# Cost model defaults (bps)
# ──────────────────────────────────────────────────────────────────────
DEFAULT_COST_PER_LEG_BPS = 0.5        # per leg, entry or exit
THIN_LIQUIDITY_SLIPPAGE_MULT = 2.0    # extra multiplier when thin
TOTAL_LEGS_PER_ROUND_TRIP = 4         # open leg A, open leg B, close A, close B

# ──────────────────────────────────────────────────────────────────────
# Liquidity thresholds
# ──────────────────────────────────────────────────────────────────────
VOLUME_THIN_THRESHOLD = 50            # fewer contracts → "thin"
OI_THIN_THRESHOLD = 100               # OI below this also → "thin"

# ──────────────────────────────────────────────────────────────────────
# Signal rule defaults
# ──────────────────────────────────────────────────────────────────────
ENTRY_Z = 2.0
EXIT_Z = 0.5
TIME_STOP_DAYS = 10
ZSCORE_WINDOW = 20                    # rolling lookback (trading days)

# ──────────────────────────────────────────────────────────────────────
# Build / Unseen split
# ──────────────────────────────────────────────────────────────────────
# Percentage of the data used for the BUILD (in-sample) period.
# The remainder is the UNSEEN (out-of-sample) period.
BUILD_FRACTION = 0.6

# ──────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND_ROOT = PROJECT_ROOT / "backend"
DATA_DIR = BACKEND_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CLEAN_DIR = DATA_DIR / "clean"
SAMPLE_DIR = DATA_DIR / "sample"
PARQUET_PATH = CLEAN_DIR / "karat.parquet"

# ──────────────────────────────────────────────────────────────────────
# MCX Bhavcopy download
# ──────────────────────────────────────────────────────────────────────
MCX_BHAVCOPY_URL = (
    "https://www.mcxindia.com/backpage.aspx/GetDatewiseBhavCopy"
)
MCX_RATE_LIMIT_SECONDS = 1.5         # minimum gap between requests
MCX_MAX_RETRIES = 3
MCX_BACKOFF_BASE = 2.0               # exponential backoff base in seconds
