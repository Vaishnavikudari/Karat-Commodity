"""
KARAT – Module 4: Contract Lifecycle & Calendar Tests.

Covers:
1. Tracking listing date, first liquid day, tender period, last trade date and expiry.
2. Validating that entries and exits fall strictly inside the valid contract calendar.
3. Rejecting/flagging trades that enter during tender periods or exit past last trade dates.
4. Correctly exposing upcoming expiries and roll windows.
"""

from __future__ import annotations

import datetime as dt
import pytest

from backend.data.parser import load_sample
from backend.calendar.lifecycle import (
    get_contract_calendar,
    validate_trade_calendar,
    get_upcoming_expiries_and_roll_windows,
)


class TestContractLifecycleCalendar:
    def test_calendar_lifecycle_fields_present(self):
        """Verify all institutional lifecycle fields are calculated for every contract expiry."""
        df = load_sample()
        cal = get_contract_calendar(df)
        assert "events" in cal
        assert len(cal["events"]) > 0
        assert "rules" in cal

        for ev in cal["events"]:
            assert "symbol" in ev
            assert "expiry_date" in ev
            assert "listing_date" in ev
            assert "first_trading_day" in ev
            assert "first_liquid_day" in ev
            assert "tender_start" in ev
            assert "last_trading_day" in ev
            assert "roll_window_start" in ev
            assert "roll_window_end" in ev
            assert "status" in ev

            # Structural date sequence check:
            # first_trading_day <= tender_start <= last_trading_day
            ftd = dt.date.fromisoformat(ev["first_trading_day"])
            ts = dt.date.fromisoformat(ev["tender_start"])
            ltd = dt.date.fromisoformat(ev["last_trading_day"])

            assert ftd <= ltd
            assert ts <= ltd


class TestTradeCalendarValidation:
    def test_valid_trade_inside_calendar(self):
        """A normal trade executed well before tender period is fully valid."""
        res = validate_trade_calendar(
            symbol="GOLDM",
            expiry_date=dt.date(2025, 2, 5),
            entry_date=dt.date(2025, 1, 2),
            exit_date=dt.date(2025, 1, 15),
        )
        assert res["is_valid"] is True
        assert len(res["violations"]) == 0
        assert res["held_in_tender"] is False

    def test_trade_rejected_if_entry_in_tender_period(self):
        """Entering inside the compulsory delivery tender notice window must be flagged/invalid."""
        # For Feb 5 expiry, tender starts ~Jan 29
        res = validate_trade_calendar(
            symbol="GOLDM",
            expiry_date=dt.date(2025, 2, 5),
            entry_date=dt.date(2025, 1, 30),
            exit_date=dt.date(2025, 2, 2),
        )
        assert res["is_valid"] is False
        assert any("tender" in v.lower() for v in res["violations"])

    def test_trade_rejected_if_exit_after_last_trade_date(self):
        """Exiting after expiry/last trading day is structurally impossible and rejected."""
        res = validate_trade_calendar(
            symbol="GOLDM",
            expiry_date=dt.date(2025, 2, 5),
            entry_date=dt.date(2025, 1, 15),
            exit_date=dt.date(2025, 2, 10),
        )
        assert res["is_valid"] is False
        assert any("last trade" in v.lower() for v in res["violations"])

    def test_goldten_entry_before_2025_listing_rejected(self):
        """GOLDTEN only listed in 2025; trading in 2024 is strictly rejected."""
        res = validate_trade_calendar(
            symbol="GOLDTEN",
            expiry_date=dt.date(2025, 2, 28),
            entry_date=dt.date(2024, 12, 1),
            exit_date=dt.date(2024, 12, 15),
        )
        assert res["is_valid"] is False
        assert any("listing start" in v.lower() for v in res["violations"])


class TestUpcomingExpiriesAndRollWindows:
    def test_upcoming_expiries_calculations(self):
        """Verify days to expiry, roll window, and tender period countdowns."""
        df = load_sample()
        as_of = dt.date(2025, 1, 10)
        upcoming = get_upcoming_expiries_and_roll_windows(df, as_of_date=as_of)

        assert len(upcoming) > 0
        for item in upcoming:
            assert "days_to_expiry" in item
            assert item["days_to_expiry"] >= 0
            assert "days_to_tender" in item
            assert "days_to_roll" in item
            assert "in_roll_window" in item
            assert "in_tender_period" in item
