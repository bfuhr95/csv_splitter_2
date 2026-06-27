"""Seed a ledger database with a realistic month of journal entries.

This script populates a company file with the default chart of accounts and a
month of balanced double-entry transactions for a small business: owner
investment, equipment bought on credit, cash and credit sales, cost of goods
sold, operating expenses (rent, wages, utilities), a customer payment, and an
owner draw.

Use it to explore the GUI with meaningful numbers in every report.

Importable::

    from sample_data import load_sample
    load_sample("ledger.db")

Runnable::

    python3.12 sample_data.py [db_path]

If ``db_path`` is omitted it defaults to ``ledger.db``. Every entry posted by
this script balances (total debits equal total credits), so the trial balance
and balance sheet always tie out.
"""

from __future__ import annotations

import sys
from decimal import Decimal

from ledger.db import seed_default_chart
from ledger.engine import Ledger


def load_sample(db_path: str = "ledger.db") -> Ledger:
    """Seed ``db_path`` with the default chart and a month of entries.

    Returns the open :class:`~ledger.engine.Ledger`. The function is safe to
    call on an empty database; ``seed_default_chart`` only inserts the chart
    when the accounts table is empty, but the sample journal entries are always
    posted, so calling this twice will create duplicate transactions.

    Every entry is balanced before it is posted; ``post_entry`` would raise
    :class:`~ledger.engine.LedgerError` otherwise.
    """
    ledger = Ledger(db_path)
    seed_default_chart(ledger)

    # Resolve account ids by their chart code so the script stays readable.
    def acct(code: str) -> int:
        account = ledger.get_account_by_code(code)
        if account is None:  # pragma: no cover - default chart guarantees these
            raise RuntimeError(f"Expected default-chart account {code!r} to exist.")
        return account.id

    cash = acct("1000")
    receivable = acct("1100")
    inventory = acct("1200")
    equipment = acct("1500")
    payable = acct("2000")
    notes_payable = acct("2100")
    owner_capital = acct("3000")
    owner_draws = acct("3100")
    sales_revenue = acct("4000")
    service_revenue = acct("4100")
    cogs = acct("5000")
    rent_expense = acct("5100")
    wages_expense = acct("5200")
    utilities_expense = acct("5300")
    office_supplies = acct("5400")

    D = Decimal

    # Each entry is (date, memo, reference, [lines]) where a line is
    # (account_id, debit, credit, line_memo). For every entry the sum of the
    # debit column equals the sum of the credit column.
    entries: list[tuple[str, str, str, list[tuple[int, Decimal, Decimal, str]]]] = [
        (
            "2026-06-01",
            "Owner invests cash to start the business",
            "JE-001",
            [
                (cash, D("25000.00"), D("0.00"), "Initial capital"),
                (owner_capital, D("0.00"), D("25000.00"), "Owner contribution"),
            ],
        ),
        (
            "2026-06-02",
            "Signed note payable for startup financing",
            "JE-002",
            [
                (cash, D("10000.00"), D("0.00"), "Loan proceeds"),
                (notes_payable, D("0.00"), D("10000.00"), "Bank note, 12 mo"),
            ],
        ),
        (
            "2026-06-03",
            "Purchased equipment on credit",
            "JE-003",
            [
                (equipment, D("8000.00"), D("0.00"), "Workshop equipment"),
                (payable, D("0.00"), D("8000.00"), "Due to ToolCo"),
            ],
        ),
        (
            "2026-06-04",
            "Purchased inventory on account",
            "JE-004",
            [
                (inventory, D("6000.00"), D("0.00"), "Merchandise for resale"),
                (payable, D("0.00"), D("6000.00"), "Due to SupplyCo"),
            ],
        ),
        (
            "2026-06-05",
            "Paid June rent",
            "JE-005",
            [
                (rent_expense, D("1800.00"), D("0.00"), "Storefront rent"),
                (cash, D("0.00"), D("1800.00"), "Rent check"),
            ],
        ),
        (
            "2026-06-06",
            "Bought office supplies for cash",
            "JE-006",
            [
                (office_supplies, D("250.00"), D("0.00"), "Paper, ink, etc."),
                (cash, D("0.00"), D("250.00"), "Supply run"),
            ],
        ),
        (
            "2026-06-10",
            "Cash sales for the week",
            "JE-007",
            [
                (cash, D("4200.00"), D("0.00"), "Register total"),
                (sales_revenue, D("0.00"), D("4200.00"), "Weekly cash sales"),
            ],
        ),
        (
            "2026-06-10",
            "Cost of goods sold on cash sales",
            "JE-008",
            [
                (cogs, D("2520.00"), D("0.00"), "COGS on weekly sales"),
                (inventory, D("0.00"), D("2520.00"), "Inventory relieved"),
            ],
        ),
        (
            "2026-06-14",
            "Sale on account to a wholesale customer",
            "JE-009",
            [
                (receivable, D("3000.00"), D("0.00"), "Invoice 1042"),
                (sales_revenue, D("0.00"), D("3000.00"), "Wholesale order"),
            ],
        ),
        (
            "2026-06-14",
            "Cost of goods sold on credit sale",
            "JE-010",
            [
                (cogs, D("1800.00"), D("0.00"), "COGS on invoice 1042"),
                (inventory, D("0.00"), D("1800.00"), "Inventory relieved"),
            ],
        ),
        (
            "2026-06-15",
            "Paid wages for the first half of June",
            "JE-011",
            [
                (wages_expense, D("2600.00"), D("0.00"), "Payroll period 1"),
                (cash, D("0.00"), D("2600.00"), "Net pay"),
            ],
        ),
        (
            "2026-06-18",
            "Provided consulting service for cash",
            "JE-012",
            [
                (cash, D("1500.00"), D("0.00"), "Service fee"),
                (service_revenue, D("0.00"), D("1500.00"), "Setup consulting"),
            ],
        ),
        (
            "2026-06-20",
            "Customer paid down their account balance",
            "JE-013",
            [
                (cash, D("2000.00"), D("0.00"), "Payment on invoice 1042"),
                (receivable, D("0.00"), D("2000.00"), "Partial collection"),
            ],
        ),
        (
            "2026-06-22",
            "Paid supplier toward accounts payable",
            "JE-014",
            [
                (payable, D("4000.00"), D("0.00"), "Pay down SupplyCo"),
                (cash, D("0.00"), D("4000.00"), "AP payment"),
            ],
        ),
        (
            "2026-06-25",
            "Paid June utilities",
            "JE-015",
            [
                (utilities_expense, D("420.00"), D("0.00"), "Electric & water"),
                (cash, D("0.00"), D("420.00"), "Utility bill"),
            ],
        ),
        (
            "2026-06-28",
            "Owner withdrew cash for personal use",
            "JE-016",
            [
                (owner_draws, D("1500.00"), D("0.00"), "June draw"),
                (cash, D("0.00"), D("1500.00"), "Owner withdrawal"),
            ],
        ),
    ]

    for date, memo, reference, lines in entries:
        ledger.post_entry(date, lines, memo=memo, reference=reference)

    return ledger


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point: ``python3.12 sample_data.py [db_path]``."""
    args = sys.argv[1:] if argv is None else argv
    db_path = args[0] if args else "ledger.db"

    ledger = load_sample(db_path)
    try:
        entries = ledger.list_entries()
        accounts = ledger.list_accounts()
        print(f"Seeded {len(accounts)} accounts and posted {len(entries)} "
              f"journal entries into {db_path!r}.")
        print("Open the GUI to explore it:  python3.12 main.py --db "
              f"{db_path}")
    finally:
        ledger.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
