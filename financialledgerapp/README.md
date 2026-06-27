# Double-Entry Accounting Ledger

A small, self-contained **double-entry bookkeeping** application with a desktop
GUI. Record journal entries, keep a chart of accounts, drill into any account's
general ledger, and generate the three core financial statements — a **trial
balance**, an **income statement**, and a **balance sheet** — with one-click CSV
export.

Built entirely on the Python standard library: `sqlite3` for storage, `decimal`
for exact money math, and `tkinter` for the interface. No third-party packages.

---

## Features

- **Chart of accounts** — add, edit, and deactivate accounts across the five
  standard types (Asset, Liability, Equity, Revenue, Expense). Ships with a
  sensible 15-account default chart.
- **Balanced journal entries** — post multi-line entries with per-line memos.
  Every entry is validated: at least two lines, exactly one of debit/credit per
  line, non-negative amounts, and **total debits must equal total credits**.
  Posting is atomic.
- **General ledger drill-down** — view every line that touched an account, in
  date order, with a running balance.
- **Financial reports** — trial balance, income statement (for any date range),
  and a balance sheet that always ties out. Each report exports to CSV.
- **Exact money** — all amounts are stored as integer cents and surfaced as
  `decimal.Decimal` dollars, so there is no floating-point drift. Values format
  with thousands separators and accounting-style parentheses for negatives,
  e.g. `1,234.56` and `(690.00)`.
- **Plain-file database** — each company is a single SQLite `.db` file you can
  copy, back up, or hand off.

---

## Requirements

- **Python 3.12**
- **Tkinter** (the `tkinter` module ships with the standard library, but on
  Debian/Ubuntu the Tk bindings are packaged separately):

  ```bash
  sudo apt install python3-tk
  ```

  On Windows and macOS, the official python.org installers already include Tk.

- **No third-party dependencies.** Standard library only — see
  [`requirements.txt`](requirements.txt).

Verify Tk is available:

```bash
python3.12 -c "import tkinter; print('tkinter ok')"
```

---

## Running the application

Launch the GUI:

```bash
python3.12 main.py
```

This opens (and, if needed, creates) `ledger.db` in the current directory. If
the database has no accounts yet, the default chart of accounts is seeded
automatically so you can start posting immediately.

Point it at a different company file with `--db`:

```bash
python3.12 main.py --db /path/to/acme.db
```

### Load the sample data

To explore the app with realistic numbers in every report, seed a database with
a full month of transactions for a small business:

```bash
python3.12 sample_data.py            # writes to ledger.db
python3.12 sample_data.py acme.db    # or a path of your choice
```

Then open it:

```bash
python3.12 main.py --db acme.db
```

The sample posts 16 balanced entries dated across June 2026 — owner investment,
a bank note, equipment and inventory bought on credit, cash and credit sales
with matching cost of goods sold, rent / wages / utilities / office supplies,
a customer payment, an accounts-payable payment, and an owner draw. After
loading, the trial balance totals **53,700.00** on each side, the income
statement shows **8,700.00** revenue against **9,390.00** expense for a net loss
of **(690.00)**, and the balance sheet ties out at **42,810.00** in assets
against **20,000.00** liabilities plus **22,810.00** equity.

You can also seed from your own code:

```python
from sample_data import load_sample

ledger = load_sample("acme.db")
print(len(ledger.list_entries()), "entries posted")
ledger.close()
```

### Run the tests

```bash
python3.12 -m unittest discover -s tests
```

---

## A quick accounting primer

If you are new to double-entry bookkeeping, here is everything you need to use
this app.

**Debits and credits.** Every transaction is recorded as a *journal entry* with
two or more *lines*. Each line is either a **debit** or a **credit**, and the
total debits in an entry must equal the total credits. This is the rule that
keeps the books in balance — the app enforces it, refusing to post any entry
that does not balance.

**The five account types and their normal sides.** Each account belongs to one
of five types. A type's *normal side* is the side on which its balance grows:

| Type      | Normal side | A debit…   | A credit…  | Examples                         |
|-----------|-------------|------------|------------|----------------------------------|
| Asset     | Debit       | increases  | decreases  | Cash, Accounts Receivable, Equipment |
| Liability | Credit      | decreases  | increases  | Accounts Payable, Notes Payable  |
| Equity    | Credit      | decreases  | increases  | Owner Capital, Owner Draws       |
| Revenue   | Credit      | decreases  | increases  | Sales Revenue, Service Revenue   |
| Expense   | Debit       | increases  | decreases  | Rent, Wages, Utilities, COGS     |

**The accounting equation.** Assets = Liabilities + Equity. Net income (revenue
− expense) flows into equity, which is why the balance sheet always balances.

**Worked example.** When the owner invests $25,000 cash to start the business:

| Account            | Debit      | Credit     |
|--------------------|-----------:|-----------:|
| 1000 Cash          | 25,000.00  |            |
| 3000 Owner Capital |            | 25,000.00  |

Cash (an asset) goes *up* with a debit; Owner Capital (equity) goes *up* with a
credit; debits equal credits, so the entry balances.

---

## Usage walkthrough

The window is a tabbed notebook with a **File** and **Help** menu.

1. **Chart of Accounts** — the starting tab. It lists every account by code with
   its name, type, and active status. Add a new account or edit/deactivate an
   existing one through a small modal dialog. Accounts that already have journal
   activity can be deactivated (to hide them from new entries) but not deleted,
   so history is never lost.

2. **Journal Entry** — record a transaction. Enter the date, an optional memo
   and reference, then fill in lines choosing an account and a debit *or* credit
   amount for each. The running totals show debits and credits side by side; the
   entry only posts when they match. Submitting writes the entry atomically.

   *Try it with the sample data:* the entry dated `2026-06-10` records weekly
   cash sales — a debit to Cash and a credit to Sales Revenue — immediately
   followed by a second entry relieving Inventory into COGS.

3. **General Ledger** — pick an account to see every line that posted to it, in
   date order, with a running balance. This is where you confirm, for example,
   that Cash rose with each sale and fell with each payment.

4. **Reports** — generate a report and export it to CSV:
   - **Trial Balance** *(as of a date)* — every account's net balance split into
     debit and credit columns; the totals must agree.
   - **Income Statement** *(for a start–end range)* — revenue less expense for
     the period, ending in net income (or a loss in parentheses).
   - **Balance Sheet** *(as of a date)* — assets against liabilities and equity.
     A synthetic *Current Earnings (Net Income)* line folds period earnings into
     equity, so the sheet always balances for any valid set of entries.

The **File** menu exports the current report to CSV and exits; **Help** shows an
about box.

---

## Architecture

The code separates a pure, fully testable backend from the Tk presentation
layer. Everything lives under the `ledger/` package plus `main.py`.

| Module             | Responsibility                                                                                   |
|--------------------|--------------------------------------------------------------------------------------------------|
| `ledger/money.py`  | Money helpers: `to_cents` / `from_cents`, accounting-style `fmt`, tolerant `parse_money`.         |
| `ledger/models.py` | Plain dataclasses — `Account`, `JournalEntry`, `JournalLine` — and the `AccountType` enum with its `normal_side`. |
| `ledger/db.py`     | SQLite connection, schema creation (money stored as integer cents), and the default chart of accounts. |
| `ledger/engine.py` | The `Ledger` service layer: account management, validated/atomic `post_entry`, balances, and ledger queries. Raises `LedgerError` on any integrity failure. |
| `ledger/reports.py`| Pure functions producing the trial balance, income statement, and balance sheet, plus CSV exporters. |
| `ledger/gui.py`    | The Tkinter `LedgerApp` (notebook tabs, dialogs) — a thin view over the engine and reports.       |
| `main.py`          | CLI entry point: parses `--db`, seeds the chart for a fresh database, and starts the GUI.          |

Because the backend has no GUI dependency, the test suite under `tests/`
exercises the engine and reports directly, including a randomized invariant
test that posts many entries and asserts the trial balance and balance sheet
always tie out.

Convenience re-exports let you reach the common API in one import:

```python
from ledger import Ledger, AccountType, trial_balance, income_statement, balance_sheet
```

---

## Project layout

```
.
├── main.py              # GUI entry point (python3.12 main.py)
├── sample_data.py       # seed a month of balanced transactions
├── requirements.txt     # (no third-party deps; tkinter via system package)
├── ledger/
│   ├── money.py
│   ├── models.py
│   ├── db.py
│   ├── engine.py
│   ├── reports.py
│   └── gui.py
└── tests/
    ├── test_ledger.py   # unit + invariant tests
    └── gui_smoke.py     # headless GUI smoke test
```
