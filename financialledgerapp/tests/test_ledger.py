"""Unit tests for the double-entry ledger backend."""

from __future__ import annotations

import os
import sys
import unittest
from decimal import Decimal

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ledger import reports
from ledger.db import DEFAULT_CHART, seed_default_chart
from ledger.engine import Ledger, LedgerError
from ledger.models import AccountType
from ledger.money import ZERO, fmt, from_cents, parse_money, to_cents


class MoneyTests(unittest.TestCase):
    def test_to_cents_rounding(self) -> None:
        self.assertEqual(to_cents("1.005"), 101)
        self.assertEqual(to_cents(Decimal("1.004")), 100)
        self.assertEqual(to_cents("10"), 1000)
        self.assertEqual(to_cents(5), 500)

    def test_from_cents(self) -> None:
        self.assertEqual(from_cents(101), Decimal("1.01"))
        self.assertEqual(from_cents(-250), Decimal("-2.50"))

    def test_roundtrip(self) -> None:
        for value in ("0.00", "1234.56", "-99.99", "0.01"):
            self.assertEqual(from_cents(to_cents(value)), Decimal(value))

    def test_fmt(self) -> None:
        self.assertEqual(fmt(Decimal("1234.56")), "1,234.56")
        self.assertEqual(fmt(Decimal("-1234.56")), "(1,234.56)")
        self.assertEqual(fmt(ZERO), "0.00")

    def test_parse_money(self) -> None:
        self.assertEqual(parse_money("$1,234.56"), Decimal("1234.56"))
        self.assertEqual(parse_money("(1,234.56)"), Decimal("-1234.56"))
        self.assertEqual(parse_money("  -5.00 "), Decimal("-5.00"))
        self.assertEqual(parse_money(""), ZERO)
        self.assertEqual(parse_money("  "), ZERO)


class AccountTypeTests(unittest.TestCase):
    def test_normal_side(self) -> None:
        self.assertEqual(AccountType.ASSET.normal_side, "DEBIT")
        self.assertEqual(AccountType.EXPENSE.normal_side, "DEBIT")
        self.assertEqual(AccountType.LIABILITY.normal_side, "CREDIT")
        self.assertEqual(AccountType.EQUITY.normal_side, "CREDIT")
        self.assertEqual(AccountType.REVENUE.normal_side, "CREDIT")


class LedgerBase(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = Ledger(":memory:")
        seed_default_chart(self.ledger)

    def tearDown(self) -> None:
        self.ledger.close()

    def code_id(self, code: str) -> int:
        return self.ledger.get_account_by_code(code).id


class AccountTests(LedgerBase):
    def test_seed_default_chart(self) -> None:
        accounts = self.ledger.list_accounts()
        self.assertEqual(len(accounts), len(DEFAULT_CHART))

    def test_seed_is_idempotent(self) -> None:
        seed_default_chart(self.ledger)
        self.assertEqual(len(self.ledger.list_accounts()), len(DEFAULT_CHART))

    def test_add_account(self) -> None:
        acct = self.ledger.add_account("9999", "Test", AccountType.ASSET)
        self.assertIsNotNone(acct.id)
        self.assertEqual(self.ledger.get_account(acct.id).name, "Test")

    def test_add_duplicate_code_rejected(self) -> None:
        with self.assertRaises(LedgerError):
            self.ledger.add_account("1000", "Dup", AccountType.ASSET)

    def test_add_blank_rejected(self) -> None:
        with self.assertRaises(LedgerError):
            self.ledger.add_account("", "X", AccountType.ASSET)
        with self.assertRaises(LedgerError):
            self.ledger.add_account("8888", "", AccountType.ASSET)

    def test_list_filters(self) -> None:
        assets = self.ledger.list_accounts(type=AccountType.ASSET)
        self.assertTrue(all(a.type == AccountType.ASSET for a in assets))
        codes = [a.code for a in self.ledger.list_accounts()]
        self.assertEqual(codes, sorted(codes))

    def test_update_account(self) -> None:
        acct = self.ledger.add_account("7000", "Old", AccountType.ASSET)
        updated = self.ledger.update_account(acct.id, name="New", code="7001")
        self.assertEqual(updated.name, "New")
        self.assertEqual(updated.code, "7001")

    def test_update_duplicate_code_rejected(self) -> None:
        acct = self.ledger.add_account("7000", "X", AccountType.ASSET)
        with self.assertRaises(LedgerError):
            self.ledger.update_account(acct.id, code="1000")

    def test_delete_account_without_activity(self) -> None:
        acct = self.ledger.add_account("7000", "X", AccountType.ASSET)
        self.ledger.delete_account(acct.id)
        self.assertIsNone(self.ledger.get_account_by_code("7000"))

    def test_delete_account_with_activity_rejected(self) -> None:
        cash = self.code_id("1000")
        cap = self.code_id("3000")
        self.ledger.post_entry(
            "2026-01-01",
            [
                {"account_id": cash, "debit": "100.00", "credit": "0"},
                {"account_id": cap, "debit": "0", "credit": "100.00"},
            ],
        )
        with self.assertRaises(LedgerError):
            self.ledger.delete_account(cash)

    def test_deactivate(self) -> None:
        cash = self.code_id("1000")
        self.ledger.deactivate_account(cash)
        self.assertFalse(self.ledger.get_account(cash).is_active)


class PostingTests(LedgerBase):
    def _simple_entry(self, amount: str = "100.00", date: str = "2026-01-01"):
        return self.ledger.post_entry(
            date,
            [
                {"account_id": self.code_id("1000"), "debit": amount, "credit": "0"},
                {"account_id": self.code_id("3000"), "debit": "0", "credit": amount},
            ],
            memo="test",
        )

    def test_post_balanced(self) -> None:
        entry = self._simple_entry()
        self.assertIsNotNone(entry.id)
        self.assertEqual(len(entry.lines), 2)
        self.assertIsNotNone(entry.created_at)
        self.assertIsNotNone(entry.lines[0].account_code)

    def test_post_requires_two_lines(self) -> None:
        with self.assertRaises(LedgerError):
            self.ledger.post_entry(
                "2026-01-01",
                [{"account_id": self.code_id("1000"), "debit": "100", "credit": "0"}],
            )

    def test_post_unbalanced_rejected(self) -> None:
        with self.assertRaises(LedgerError):
            self.ledger.post_entry(
                "2026-01-01",
                [
                    {"account_id": self.code_id("1000"), "debit": "100", "credit": "0"},
                    {"account_id": self.code_id("3000"), "debit": "0", "credit": "90"},
                ],
            )

    def test_post_both_sides_rejected(self) -> None:
        with self.assertRaises(LedgerError):
            self.ledger.post_entry(
                "2026-01-01",
                [
                    {"account_id": self.code_id("1000"), "debit": "100", "credit": "100"},
                    {"account_id": self.code_id("3000"), "debit": "0", "credit": "100"},
                ],
            )

    def test_post_zero_total_rejected(self) -> None:
        with self.assertRaises(LedgerError):
            self.ledger.post_entry(
                "2026-01-01",
                [
                    {"account_id": self.code_id("1000"), "debit": "0", "credit": "0"},
                    {"account_id": self.code_id("3000"), "debit": "0", "credit": "0"},
                ],
            )

    def test_post_bad_date_rejected(self) -> None:
        with self.assertRaises(LedgerError):
            self._simple_entry(date="not-a-date")

    def test_post_unknown_account_rejected(self) -> None:
        with self.assertRaises(LedgerError):
            self.ledger.post_entry(
                "2026-01-01",
                [
                    {"account_id": 999999, "debit": "100", "credit": "0"},
                    {"account_id": self.code_id("3000"), "debit": "0", "credit": "100"},
                ],
            )

    def test_tuple_and_dataclass_lines(self) -> None:
        from ledger.models import JournalLine

        entry = self.ledger.post_entry(
            "2026-01-01",
            [
                (self.code_id("1000"), Decimal("50.00"), ZERO, "tuple line"),
                JournalLine(self.code_id("3000"), credit=Decimal("50.00")),
            ],
        )
        self.assertEqual(len(entry.lines), 2)

    def test_list_entries_newest_first(self) -> None:
        self._simple_entry(date="2026-01-01")
        self._simple_entry(date="2026-03-01")
        entries = self.ledger.list_entries()
        self.assertEqual(entries[0].date, "2026-03-01")

    def test_list_entries_date_range(self) -> None:
        self._simple_entry(date="2026-01-01")
        self._simple_entry(date="2026-06-01")
        entries = self.ledger.list_entries(start="2026-05-01", end="2026-12-31")
        self.assertEqual(len(entries), 1)

    def test_delete_entry(self) -> None:
        entry = self._simple_entry()
        self.ledger.delete_entry(entry.id)
        with self.assertRaises(LedgerError):
            self.ledger.get_entry(entry.id)


class BalanceTests(LedgerBase):
    def test_raw_and_account_balance(self) -> None:
        cash = self.code_id("1000")
        cap = self.code_id("3000")
        self.ledger.post_entry(
            "2026-01-01",
            [
                {"account_id": cash, "debit": "1000.00", "credit": "0"},
                {"account_id": cap, "debit": "0", "credit": "1000.00"},
            ],
        )
        self.assertEqual(self.ledger.raw_balance(cash), Decimal("1000.00"))
        self.assertEqual(self.ledger.account_balance(cash), Decimal("1000.00"))
        # Equity raw is negative (credit), but normal-side positive.
        self.assertEqual(self.ledger.raw_balance(cap), Decimal("-1000.00"))
        self.assertEqual(self.ledger.account_balance(cap), Decimal("1000.00"))

    def test_as_of_filter(self) -> None:
        cash = self.code_id("1000")
        cap = self.code_id("3000")
        self.ledger.post_entry(
            "2026-01-01",
            [
                {"account_id": cash, "debit": "100.00", "credit": "0"},
                {"account_id": cap, "debit": "0", "credit": "100.00"},
            ],
        )
        self.ledger.post_entry(
            "2026-06-01",
            [
                {"account_id": cash, "debit": "50.00", "credit": "0"},
                {"account_id": cap, "debit": "0", "credit": "50.00"},
            ],
        )
        self.assertEqual(
            self.ledger.raw_balance(cash, as_of="2026-03-01"), Decimal("100.00")
        )
        self.assertEqual(self.ledger.raw_balance(cash), Decimal("150.00"))

    def test_ledger_lines_running(self) -> None:
        cash = self.code_id("1000")
        cap = self.code_id("3000")
        ar = self.code_id("1100")
        self.ledger.post_entry(
            "2026-01-01",
            [
                {"account_id": cash, "debit": "100.00", "credit": "0"},
                {"account_id": cap, "debit": "0", "credit": "100.00"},
            ],
        )
        self.ledger.post_entry(
            "2026-02-01",
            [
                {"account_id": ar, "debit": "40.00", "credit": "0"},
                {"account_id": cash, "debit": "0", "credit": "40.00"},
            ],
        )
        rows = self.ledger.ledger_lines(cash)
        self.assertEqual(rows[0].running_balance, Decimal("100.00"))
        self.assertEqual(rows[1].running_balance, Decimal("60.00"))

    def test_totals_by_type(self) -> None:
        cash = self.code_id("1000")
        cap = self.code_id("3000")
        self.ledger.post_entry(
            "2026-01-01",
            [
                {"account_id": cash, "debit": "200.00", "credit": "0"},
                {"account_id": cap, "debit": "0", "credit": "200.00"},
            ],
        )
        totals = self.ledger.totals_by_type()
        self.assertEqual(totals[AccountType.ASSET], Decimal("200.00"))
        self.assertEqual(totals[AccountType.EQUITY], Decimal("200.00"))


class ReportTests(LedgerBase):
    def _build_business(self) -> None:
        cash = self.code_id("1000")
        cap = self.code_id("3000")
        sales = self.code_id("4000")
        rent = self.code_id("5100")
        ar = self.code_id("1100")
        ap = self.code_id("2000")
        # Owner invests 10,000.
        self.ledger.post_entry(
            "2026-01-01",
            [
                {"account_id": cash, "debit": "10000.00", "credit": "0"},
                {"account_id": cap, "debit": "0", "credit": "10000.00"},
            ],
        )
        # Sale on account 3,000.
        self.ledger.post_entry(
            "2026-02-01",
            [
                {"account_id": ar, "debit": "3000.00", "credit": "0"},
                {"account_id": sales, "debit": "0", "credit": "3000.00"},
            ],
        )
        # Pay rent 1,200 on account.
        self.ledger.post_entry(
            "2026-03-01",
            [
                {"account_id": rent, "debit": "1200.00", "credit": "0"},
                {"account_id": ap, "debit": "0", "credit": "1200.00"},
            ],
        )

    def test_trial_balance_balanced(self) -> None:
        self._build_business()
        tb = reports.trial_balance(self.ledger)
        self.assertTrue(tb.is_balanced)
        self.assertEqual(tb.total_debit, tb.total_credit)
        self.assertGreater(tb.total_debit, ZERO)

    def test_trial_balance_skips_zero(self) -> None:
        self._build_business()
        tb = reports.trial_balance(self.ledger)
        codes = {acct.code for acct, _, _ in tb.rows}
        self.assertNotIn("1200", codes)  # Inventory never used.

    def test_income_statement(self) -> None:
        self._build_business()
        is_ = reports.income_statement(self.ledger, "2026-01-01", "2026-12-31")
        self.assertEqual(is_.total_revenue, Decimal("3000.00"))
        self.assertEqual(is_.total_expense, Decimal("1200.00"))
        self.assertEqual(is_.net_income, Decimal("1800.00"))

    def test_income_statement_period_filter(self) -> None:
        self._build_business()
        is_ = reports.income_statement(self.ledger, "2026-01-01", "2026-01-31")
        self.assertEqual(is_.total_revenue, ZERO)

    def test_balance_sheet_balances(self) -> None:
        self._build_business()
        bs = reports.balance_sheet(self.ledger)
        self.assertTrue(bs.is_balanced)
        self.assertEqual(
            bs.total_assets, bs.total_liabilities + bs.total_equity
        )

    def test_balance_sheet_current_earnings(self) -> None:
        self._build_business()
        bs = reports.balance_sheet(self.ledger)
        labels = {label for label, _ in bs.equity}
        self.assertIn(reports.CURRENT_EARNINGS_LABEL, labels)

    def test_balance_sheet_invariant_random(self) -> None:
        # Many varied entries must still balance.
        import random

        codes = [c for c, _, _ in DEFAULT_CHART]
        for i in range(40):
            a, b = random.sample(codes, 2)
            amount = f"{random.randint(1, 9999)}.{random.randint(0, 99):02d}"
            try:
                self.ledger.post_entry(
                    f"2026-{(i % 12) + 1:02d}-15",
                    [
                        {"account_id": self.code_id(a), "debit": amount, "credit": "0"},
                        {"account_id": self.code_id(b), "debit": "0", "credit": amount},
                    ],
                )
            except LedgerError:
                continue
        bs = reports.balance_sheet(self.ledger)
        self.assertTrue(bs.is_balanced)
        tb = reports.trial_balance(self.ledger)
        self.assertTrue(tb.is_balanced)


class CsvExportTests(LedgerBase):
    def test_exports(self) -> None:
        import tempfile

        cash = self.code_id("1000")
        cap = self.code_id("3000")
        self.ledger.post_entry(
            "2026-01-01",
            [
                {"account_id": cash, "debit": "500.00", "credit": "0"},
                {"account_id": cap, "debit": "0", "credit": "500.00"},
            ],
        )
        tb = reports.trial_balance(self.ledger)
        is_ = reports.income_statement(self.ledger, "2026-01-01", "2026-12-31")
        bs = reports.balance_sheet(self.ledger)
        with tempfile.TemporaryDirectory() as d:
            reports.export_trial_balance_csv(tb, os.path.join(d, "tb.csv"))
            reports.export_income_statement_csv(is_, os.path.join(d, "is.csv"))
            reports.export_balance_sheet_csv(bs, os.path.join(d, "bs.csv"))
            for name in ("tb.csv", "is.csv", "bs.csv"):
                self.assertTrue(os.path.getsize(os.path.join(d, name)) > 0)


if __name__ == "__main__":
    unittest.main()
