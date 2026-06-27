"""Money handling utilities for the double-entry ledger.

Money is represented as :class:`decimal.Decimal` dollars at every public API
boundary and stored in SQLite as INTEGER cents to avoid floating point error.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Union

# A monetary value accepted by the tolerant conversion helpers.
MoneyLike = Union[Decimal, int, str]

# Canonical zero value, quantized to two decimal places.
ZERO: Decimal = Decimal("0.00")

# Quantization target for dollars-and-cents.
_CENTS = Decimal("0.01")


def to_cents(value: MoneyLike) -> int:
    """Convert a dollar value to an integer number of cents.

    Accepts :class:`Decimal`, ``int``, or ``str``. Uses ROUND_HALF_UP after
    quantizing to two decimal places so that, e.g., ``"1.005"`` becomes
    ``101`` cents.
    """
    dollars = value if isinstance(value, Decimal) else Decimal(str(value))
    quantized = dollars.quantize(_CENTS, rounding=ROUND_HALF_UP)
    return int(quantized * 100)


def from_cents(cents: int) -> Decimal:
    """Convert an integer number of cents back to a quantized dollar Decimal."""
    return (Decimal(int(cents)) / 100).quantize(_CENTS, rounding=ROUND_HALF_UP)


def fmt(value: MoneyLike) -> str:
    """Format a dollar value for display.

    Uses thousands separators and two decimal places. Negative values are
    rendered in accounting parentheses style, e.g. ``"(1,234.56)"``.
    """
    dollars = value if isinstance(value, Decimal) else Decimal(str(value))
    dollars = dollars.quantize(_CENTS, rounding=ROUND_HALF_UP)
    negative = dollars < 0
    magnitude = -dollars if negative else dollars
    rendered = f"{magnitude:,.2f}"
    return f"({rendered})" if negative else rendered


def parse_money(text: str) -> Decimal:
    """Parse a user-entered money string into a quantized Decimal.

    Tolerant of currency symbols, thousands separators, surrounding
    whitespace, and accounting-style parentheses for negatives. An empty or
    whitespace-only string parses to :data:`ZERO`.
    """
    if text is None:
        return ZERO
    cleaned = str(text).strip()
    if not cleaned:
        return ZERO

    negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        negative = True
        cleaned = cleaned[1:-1]

    cleaned = cleaned.replace("$", "").replace(",", "").replace(" ", "").strip()
    if cleaned.startswith("-"):
        negative = not negative
        cleaned = cleaned[1:]
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    if not cleaned:
        return ZERO

    value = Decimal(cleaned)
    if negative:
        value = -value
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)
