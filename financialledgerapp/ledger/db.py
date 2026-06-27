"""SQLite persistence layer: connection, schema, and default chart of accounts."""

from __future__ import annotations

import sqlite3

from .models import AccountType

# Standard chart of accounts seeded into a fresh company file.
# Each tuple is (code, name, AccountType).
DEFAULT_CHART: list[tuple[str, str, AccountType]] = [
    ("1000", "Cash", AccountType.ASSET),
    ("1100", "Accounts Receivable", AccountType.ASSET),
    ("1200", "Inventory", AccountType.ASSET),
    ("1500", "Equipment", AccountType.ASSET),
    ("2000", "Accounts Payable", AccountType.LIABILITY),
    ("2100", "Notes Payable", AccountType.LIABILITY),
    ("3000", "Owner Capital", AccountType.EQUITY),
    ("3100", "Owner Draws", AccountType.EQUITY),
    ("4000", "Sales Revenue", AccountType.REVENUE),
    ("4100", "Service Revenue", AccountType.REVENUE),
    ("5000", "COGS", AccountType.EXPENSE),
    ("5100", "Rent Expense", AccountType.EXPENSE),
    ("5200", "Wages Expense", AccountType.EXPENSE),
    ("5300", "Utilities Expense", AccountType.EXPENSE),
    ("5400", "Office Supplies", AccountType.EXPENSE),
]

_ACCOUNT_TYPE_VALUES = ", ".join(f"'{t.value}'" for t in AccountType)


def connect(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with row access by name and FK enforcement."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create the ledger tables if they do not already exist."""
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL CHECK (type IN ({_ACCOUNT_TYPE_VALUES})),
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS journal_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            memo TEXT NOT NULL DEFAULT '',
            reference TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS journal_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL
                REFERENCES journal_entries(id) ON DELETE CASCADE,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            debit INTEGER NOT NULL DEFAULT 0,
            credit INTEGER NOT NULL DEFAULT 0,
            line_memo TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_lines_entry ON journal_lines(entry_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_lines_account ON journal_lines(account_id)"
    )
    conn.commit()


def seed_default_chart(ledger_or_conn) -> None:
    """Insert :data:`DEFAULT_CHART` if the accounts table is empty.

    Accepts either a :class:`~ledger.engine.Ledger` (uses its ``.conn``) or a
    raw :class:`sqlite3.Connection`.
    """
    conn = getattr(ledger_or_conn, "conn", ledger_or_conn)
    existing = conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()
    if existing["n"] > 0:
        return
    conn.executemany(
        "INSERT INTO accounts (code, name, type, is_active) VALUES (?, ?, ?, 1)",
        [(code, name, acct_type.value) for code, name, acct_type in DEFAULT_CHART],
    )
    conn.commit()
