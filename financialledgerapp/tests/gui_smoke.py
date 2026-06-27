"""Headless smoke test for the ledger GUI.

Builds the application, exercises core flows without ``mainloop``, and exits 0
on success or nonzero on any error. Designed to run under::

    xvfb-run -a python3.12 tests/gui_smoke.py
"""

from __future__ import annotations

import os
import sys
import tempfile

# Ensure the repo root is importable when run as a script.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ledger.db import seed_default_chart
from ledger.gui import LedgerApp
from ledger.models import AccountType


def main() -> int:
    """Run the smoke test, returning a process exit code."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name

    app = LedgerApp(db_path=db_path)
    try:
        app.update_idletasks()
        app.update()

        # Seed default chart and refresh.
        seed_default_chart(app.ledger)
        app.refresh_all()
        app.update_idletasks()
        app.update()

        # Create a custom account through the engine.
        app.ledger.add_account("9000", "Smoke Test Account", AccountType.EXPENSE)
        app.refresh_all()

        # Post a balanced entry through the engine.
        cash = app.ledger.get_account_by_code("1000")
        capital = app.ledger.get_account_by_code("3000")
        app.ledger.post_entry(
            "2026-01-01",
            [
                {"account_id": cash.id, "debit": "2500.00", "credit": "0"},
                {"account_id": capital.id, "debit": "0", "credit": "2500.00"},
            ],
            memo="Smoke initial capital",
        )
        app.refresh_all()
        app.update_idletasks()
        app.update()

        # Switch through every tab.
        for index in range(len(app.notebook.tabs())):
            app.notebook.select(index)
            app.update_idletasks()
            app.update()

        # Drive the general ledger view for cash.
        app.gl_account.set(f"{cash.code} - {cash.name}")
        app._gl_show()
        app.update()

        # Generate each report.
        for kind in ("trial_balance", "balance_sheet", "income_statement"):
            app.report_kind.set(kind)
            if kind == "income_statement":
                app.report_start.set("2026-01-01")
                app.report_as_of.set("2026-12-31")
            app._report_generate()
            app.update_idletasks()
            app.update()

        print("GUI smoke test passed.")
        return 0
    finally:
        app.destroy()
        try:
            os.unlink(db_path)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
