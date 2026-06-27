"""Financial reports built as pure functions over a :class:`Ledger`.

Includes the trial balance, income statement, and balance sheet, plus CSV
export helpers. The balance sheet is constructed so that it always balances
for any valid set of posted entries.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from decimal import Decimal

from .engine import Ledger
from .models import Account, AccountType
from .money import ZERO, fmt

# Label used for the synthetic equity line that captures period earnings.
CURRENT_EARNINGS_LABEL = "Current Earnings (Net Income)"


# ---------------------------------------------------------------------- #
# Trial balance
# ---------------------------------------------------------------------- #
@dataclass
class TrialBalance:
    """A trial balance as of a given date."""

    as_of: str | None
    rows: list[tuple[Account, Decimal, Decimal]] = field(default_factory=list)
    total_debit: Decimal = ZERO
    total_credit: Decimal = ZERO

    @property
    def is_balanced(self) -> bool:
        """True when total debits equal total credits."""
        return self.total_debit == self.total_credit


def trial_balance(ledger: Ledger, as_of: str | None = None) -> TrialBalance:
    """Build a trial balance from raw account balances.

    For each account ``net = raw_balance``; a positive net lands in the debit
    column and a negative net (as its absolute value) in the credit column.
    Accounts with zero net and no activity are skipped.
    """
    report = TrialBalance(as_of=as_of)
    total_debit = ZERO
    total_credit = ZERO
    for account in ledger.list_accounts():
        net = ledger.raw_balance(account.id, as_of=as_of)
        if net == ZERO and not ledger.account_has_activity(account.id):
            continue
        if net == ZERO:
            continue
        if net >= 0:
            debit, credit = net, ZERO
        else:
            debit, credit = ZERO, -net
        report.rows.append((account, debit, credit))
        total_debit += debit
        total_credit += credit
    report.total_debit = total_debit
    report.total_credit = total_credit
    return report


# ---------------------------------------------------------------------- #
# Income statement
# ---------------------------------------------------------------------- #
@dataclass
class IncomeStatement:
    """Revenue and expense activity over a reporting period."""

    start: str
    end: str
    revenue: list[tuple[Account, Decimal]] = field(default_factory=list)
    expense: list[tuple[Account, Decimal]] = field(default_factory=list)
    total_revenue: Decimal = ZERO
    total_expense: Decimal = ZERO
    net_income: Decimal = ZERO


def _period_balance(
    ledger: Ledger, account: Account, start: str, end: str
) -> Decimal:
    """Normal-side account balance restricted to entries in [start, end]."""
    lines = ledger.ledger_lines(account.id, start=start, end=end)
    raw = sum((row.debit - row.credit for row in lines), ZERO)
    return raw if account.type.normal_side == "DEBIT" else -raw


def income_statement(ledger: Ledger, start: str, end: str) -> IncomeStatement:
    """Build an income statement for the inclusive period [start, end]."""
    report = IncomeStatement(start=start, end=end)
    for account in ledger.list_accounts(type=AccountType.REVENUE):
        amount = _period_balance(ledger, account, start, end)
        if amount != ZERO:
            report.revenue.append((account, amount))
            report.total_revenue += amount
    for account in ledger.list_accounts(type=AccountType.EXPENSE):
        amount = _period_balance(ledger, account, start, end)
        if amount != ZERO:
            report.expense.append((account, amount))
            report.total_expense += amount
    report.net_income = report.total_revenue - report.total_expense
    return report


# ---------------------------------------------------------------------- #
# Balance sheet
# ---------------------------------------------------------------------- #
@dataclass
class BalanceSheet:
    """A balance sheet as of a given date.

    ``equity`` includes a synthetic current-earnings line so that the sheet
    always balances for any valid set of posted entries.
    """

    as_of: str | None
    assets: list[tuple[str, Decimal]] = field(default_factory=list)
    liabilities: list[tuple[str, Decimal]] = field(default_factory=list)
    equity: list[tuple[str, Decimal]] = field(default_factory=list)
    total_assets: Decimal = ZERO
    total_liabilities: Decimal = ZERO
    total_equity: Decimal = ZERO

    @property
    def is_balanced(self) -> bool:
        """True when assets equal liabilities plus equity."""
        return self.total_assets == self.total_liabilities + self.total_equity


def balance_sheet(ledger: Ledger, as_of: str | None = None) -> BalanceSheet:
    """Build a balance sheet that always balances.

    Asset, liability, and equity accounts contribute their normal-side
    balances. A synthetic "Current Earnings (Net Income)" line equal to
    all-time revenue minus all-time expense (up to ``as_of``) is folded into
    equity so that assets = liabilities + equity.
    """
    report = BalanceSheet(as_of=as_of)

    total_assets = ZERO
    for account in ledger.list_accounts(type=AccountType.ASSET):
        amount = ledger.account_balance(account.id, as_of=as_of)
        if amount != ZERO:
            report.assets.append((f"{account.code} {account.name}", amount))
        total_assets += amount

    total_liabilities = ZERO
    for account in ledger.list_accounts(type=AccountType.LIABILITY):
        amount = ledger.account_balance(account.id, as_of=as_of)
        if amount != ZERO:
            report.liabilities.append((f"{account.code} {account.name}", amount))
        total_liabilities += amount

    total_equity = ZERO
    for account in ledger.list_accounts(type=AccountType.EQUITY):
        amount = ledger.account_balance(account.id, as_of=as_of)
        if amount != ZERO:
            report.equity.append((f"{account.code} {account.name}", amount))
        total_equity += amount

    # Fold revenue/expense (net income) into equity so the sheet balances.
    revenue_total = sum(
        (ledger.account_balance(a.id, as_of=as_of)
         for a in ledger.list_accounts(type=AccountType.REVENUE)),
        ZERO,
    )
    expense_total = sum(
        (ledger.account_balance(a.id, as_of=as_of)
         for a in ledger.list_accounts(type=AccountType.EXPENSE)),
        ZERO,
    )
    current_earnings = revenue_total - expense_total
    report.equity.append((CURRENT_EARNINGS_LABEL, current_earnings))
    total_equity += current_earnings

    report.total_assets = total_assets
    report.total_liabilities = total_liabilities
    report.total_equity = total_equity
    return report


# ---------------------------------------------------------------------- #
# CSV export helpers
# ---------------------------------------------------------------------- #
def export_trial_balance_csv(tb: TrialBalance, path: str) -> None:
    """Write a trial balance to ``path`` as CSV."""
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Code", "Account", "Debit", "Credit"])
        for account, debit, credit in tb.rows:
            writer.writerow([
                account.code,
                account.name,
                fmt(debit) if debit != ZERO else "",
                fmt(credit) if credit != ZERO else "",
            ])
        writer.writerow(["", "TOTAL", fmt(tb.total_debit), fmt(tb.total_credit)])
        writer.writerow(["", "Balanced", str(tb.is_balanced), ""])


def export_income_statement_csv(is_: IncomeStatement, path: str) -> None:
    """Write an income statement to ``path`` as CSV."""
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Income Statement", f"{is_.start} to {is_.end}"])
        writer.writerow([])
        writer.writerow(["Revenue", "Amount"])
        for account, amount in is_.revenue:
            writer.writerow([f"{account.code} {account.name}", fmt(amount)])
        writer.writerow(["Total Revenue", fmt(is_.total_revenue)])
        writer.writerow([])
        writer.writerow(["Expense", "Amount"])
        for account, amount in is_.expense:
            writer.writerow([f"{account.code} {account.name}", fmt(amount)])
        writer.writerow(["Total Expense", fmt(is_.total_expense)])
        writer.writerow([])
        writer.writerow(["Net Income", fmt(is_.net_income)])


def export_balance_sheet_csv(bs: BalanceSheet, path: str) -> None:
    """Write a balance sheet to ``path`` as CSV."""
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Balance Sheet", f"As of {bs.as_of or 'latest'}"])
        writer.writerow([])
        writer.writerow(["Assets", "Amount"])
        for label, amount in bs.assets:
            writer.writerow([label, fmt(amount)])
        writer.writerow(["Total Assets", fmt(bs.total_assets)])
        writer.writerow([])
        writer.writerow(["Liabilities", "Amount"])
        for label, amount in bs.liabilities:
            writer.writerow([label, fmt(amount)])
        writer.writerow(["Total Liabilities", fmt(bs.total_liabilities)])
        writer.writerow([])
        writer.writerow(["Equity", "Amount"])
        for label, amount in bs.equity:
            writer.writerow([label, fmt(amount)])
        writer.writerow(["Total Equity", fmt(bs.total_equity)])
        writer.writerow([])
        writer.writerow(["Balanced", str(bs.is_balanced)])
