"""
KARAT – Calendar module forwarder for backwards compatibility.
"""
from backend.calendar.lifecycle import (
    get_contract_calendar,
    validate_trade_calendar,
    get_upcoming_expiries_and_roll_windows,
)

__all__ = [
    "get_contract_calendar",
    "validate_trade_calendar",
    "get_upcoming_expiries_and_roll_windows",
]
