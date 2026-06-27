"""Domain model dataclasses and enums for the double-entry ledger."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from .money import ZERO


class AccountType(Enum):
    """The five fundamental account classifications."""

    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"

    @property
    def normal_side(self) -> str:
        """Return the normal balance side: "DEBIT" for ASSET/EXPENSE else "CREDIT"."""
        if self in (AccountType.ASSET, AccountType.EXPENSE):
            return "DEBIT"
        return "CREDIT"


@dataclass
class Account:
    """A chart-of-accounts entry."""

    id: int | None
    code: str
    name: str
    type: AccountType
    is_active: bool = True


@dataclass
class JournalLine:
    """A single debit or credit line within a journal entry.

    Exactly one of ``debit`` / ``credit`` is greater than zero for a valid line.
    ``account_code`` and ``account_name`` are populated on read for display.
    """

    account_id: int
    debit: Decimal = ZERO
    credit: Decimal = ZERO
    line_memo: str = ""
    id: int | None = None
    account_code: str | None = None
    account_name: str | None = None


@dataclass
class JournalEntry:
    """A balanced double-entry transaction composed of journal lines."""

    id: int | None
    date: str
    memo: str
    reference: str
    lines: list[JournalLine] = field(default_factory=list)
    created_at: str | None = None
