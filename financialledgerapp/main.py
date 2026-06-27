"""Entry point for the double-entry accounting ledger desktop application.

Run with::

    python3.12 main.py [--db PATH]
"""

from __future__ import annotations

import argparse

from ledger.db import seed_default_chart
from ledger.engine import Ledger
from ledger.gui import LedgerApp


def _database_is_empty(db_path: str) -> bool:
    """Return True if the database has no accounts yet."""
    ledger = Ledger(db_path)
    try:
        return len(ledger.list_accounts()) == 0
    finally:
        ledger.close()


def main() -> None:
    """Parse arguments, optionally seed the chart, and launch the GUI."""
    parser = argparse.ArgumentParser(description="Double-entry accounting ledger.")
    parser.add_argument(
        "--db",
        default="ledger.db",
        help="Path to the SQLite database file (default: ledger.db).",
    )
    args = parser.parse_args()

    if _database_is_empty(args.db):
        # Seed a default chart so a brand-new company is immediately usable.
        seeder = Ledger(args.db)
        try:
            seed_default_chart(seeder)
        finally:
            seeder.close()

    app = LedgerApp(db_path=args.db)
    app.mainloop()


if __name__ == "__main__":
    main()
