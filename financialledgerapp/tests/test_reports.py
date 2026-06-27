"""Unit tests for ledger.reports: trial balance, income statement, balance sheet."""

from __future__ import annotations

import csv
import os
import random
import tempfile
import unittest
from decimal import Decimal

from ledger import db
from ledger.engine import Ledger
from ledger.models import AccountType
from ledger.money import ZERO
from ledger.reports import (
    CURRENT_EARNINGS_LABEL,
    balance_sheet,
    export_balance_sheet_csv,
    export_income_statement_csv,
    export_trial_balance_csv,
    income_statement,
    trial_balance,
)


class ReportTestBase(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger(":memory:")
        db.seed_default_chart(self.ledger)
        self.cash = self.ledger.get_account_by_code("1000").id
        self.ar = self.ledger.get_account_by_code("1100").id
        self.ap = self.ledger.get_account_by_code("2000").id
        self.capital = self.ledger.get_account_by_code("3000").id
        self.draws = self.ledger.get_account_by_code("3100").id
        self.revenue = self.ledger.get_account_by_code("4000").id
        self.service = self.ledger.get_account_by_code("4100").id
        self.rent = self.ledger.get_account_by_code("5100").id
        self.wages = self.ledger.get_account_by_code("5200").id

    def tearDown(self):
        self.ledger.close()

    def _build_scenario(self):
        """Investment, cash sale, sale on account, expense on account, draw."""
        self.ledger.post_entry(
            "2026-01-01",
            [(self.cash, Decimal("1000"), 0), (self.capital, 0, Decimal("1000"))],
            memo="owner investment",
        )
        self.ledger.post_entry(
            "2026-01-10",
            [(self.cash, Decimal("300"), 0), (self.revenue, 0, Decimal("300"))],
            memo="cash sale",
        )
        self.ledger.post_entry(
            "2026-02-01",
            [(self.ar, Decimal("200"), 0), (self.service, 0, Decimal("200"))],
            memo="service on account",
        )
        self.ledger.post_entry(
            "2026-02-15",
            [(self.rent, Decimal("150"), 0), (self.ap, 0, Decimal("150"))],
            memo="rent on account",
        )
        self.ledger.post_entry(
            "2026-03-01",
            [(self.draws, Decimal("75"), 0), (self.cash, 0, Decimal("75"))],
            memo="owner draw",
        )


class TrialBalanceTest(ReportTestBase):
    def test_balanced_and_equal_totals(self):
        self._build_scenario()
        tb = trial_balance(self.ledger)
        self.assertTrue(tb.is_balanced)
        self.assertEqual(tb.total_debit, tb.total_credit)

    def test_totals_match_hand_computation(self):
        self._build_scenario()
        tb = trial_balance(self.ledger)
        # Debit-side raw balances: cash 1225, AR 200, rent 150, draws 75 = 1650.
        # Credit-side raw balances: capital 1000, revenue 300, service 200,
        #                           AP 150 = 1650.
        self.assertEqual(tb.total_debit, Decimal("1650.00"))
        self.assertEqual(tb.total_credit, Decimal("1650.00"))

    def test_zero_net_accounts_skipped(self):
        self._build_scenario()
        tb = trial_balance(self.ledger)
        coded = {acct.code for acct, _d, _c in tb.rows}
        # Inventory (1200) never touched -> excluded.
        self.assertNotIn("1200", coded)

    def test_each_row_single_column(self):
        self._build_scenario()
        tb = trial_balance(self.ledger)
        for _acct, debit, credit in tb.rows:
            self.assertTrue((debit == ZERO) != (credit == ZERO))

    def test_as_of_restricts(self):
        self._build_scenario()
        tb = trial_balance(self.ledger, as_of="2026-01-31")
        # Only the January investment + cash sale exist by then.
        self.assertEqual(tb.total_debit, Decimal("1300.00"))
        self.assertEqual(tb.total_credit, Decimal("1300.00"))
        self.assertTrue(tb.is_balanced)

    def test_empty_ledger_balances(self):
        tb = trial_balance(self.ledger)
        self.assertEqual(tb.total_debit, ZERO)
        self.assertEqual(tb.total_credit, ZERO)
        self.assertTrue(tb.is_balanced)
        self.assertEqual(tb.rows, [])


class IncomeStatementTest(ReportTestBase):
    def test_net_income_equals_revenue_minus_expense(self):
        self._build_scenario()
        is_ = income_statement(self.ledger, "2026-01-01", "2026-12-31")
        self.assertEqual(is_.total_revenue, Decimal("500.00"))  # 300 + 200
        self.assertEqual(is_.total_expense, Decimal("150.00"))  # rent
        self.assertEqual(is_.net_income, Decimal("350.00"))
        self.assertEqual(is_.net_income, is_.total_revenue - is_.total_expense)

    def test_respects_date_range(self):
        self._build_scenario()
        # Only the January cash sale revenue counts; no expenses in January.
        jan = income_statement(self.ledger, "2026-01-01", "2026-01-31")
        self.assertEqual(jan.total_revenue, Decimal("300.00"))
        self.assertEqual(jan.total_expense, ZERO)
        self.assertEqual(jan.net_income, Decimal("300.00"))

    def test_february_window(self):
        self._build_scenario()
        feb = income_statement(self.ledger, "2026-02-01", "2026-02-28")
        # Service revenue 200, rent expense 150.
        self.assertEqual(feb.total_revenue, Decimal("200.00"))
        self.assertEqual(feb.total_expense, Decimal("150.00"))
        self.assertEqual(feb.net_income, Decimal("50.00"))

    def test_only_nonzero_accounts_listed(self):
        self._build_scenario()
        is_ = income_statement(self.ledger, "2026-01-01", "2026-12-31")
        rev_codes = {a.code for a, _ in is_.revenue}
        self.assertEqual(rev_codes, {"4000", "4100"})
        exp_codes = {a.code for a, _ in is_.expense}
        self.assertEqual(exp_codes, {"5100"})

    def test_loss_is_negative(self):
        # Expense exceeds revenue -> negative net income.
        self.ledger.post_entry(
            "2026-04-01",
            [(self.wages, Decimal("500"), 0), (self.cash, 0, Decimal("500"))],
        )
        is_ = income_statement(self.ledger, "2026-04-01", "2026-04-30")
        self.assertEqual(is_.net_income, Decimal("-500.00"))


class BalanceSheetInvariantTest(ReportTestBase):
    def _assert_balanced(self, bs):
        self.assertTrue(bs.is_balanced)
        self.assertEqual(bs.total_assets, bs.total_liabilities + bs.total_equity)

    def test_balances_after_full_scenario(self):
        self._build_scenario()
        bs = balance_sheet(self.ledger)
        self._assert_balanced(bs)
        # Assets: cash 1225 + AR 200 = 1425.
        self.assertEqual(bs.total_assets, Decimal("1425.00"))
        # Liabilities: AP 150.
        self.assertEqual(bs.total_liabilities, Decimal("150.00"))
        # Equity: capital 1000 - draws 75 + current earnings 350 = 1275.
        self.assertEqual(bs.total_equity, Decimal("1275.00"))

    def test_current_earnings_line_present(self):
        self._build_scenario()
        bs = balance_sheet(self.ledger)
        labels = [label for label, _amt in bs.equity]
        self.assertIn(CURRENT_EARNINGS_LABEL, labels)
        earnings = dict(bs.equity)[CURRENT_EARNINGS_LABEL]
        self.assertEqual(earnings, Decimal("350.00"))

    def test_balances_with_only_revenue(self):
        self.ledger.post_entry(
            "2026-01-01",
            [(self.cash, Decimal("400"), 0), (self.revenue, 0, Decimal("400"))],
        )
        self._assert_balanced(balance_sheet(self.ledger))

    def test_balances_with_only_expense_and_draws(self):
        self.ledger.post_entry(
            "2026-01-01",
            [(self.cash, Decimal("1000"), 0), (self.capital, 0, Decimal("1000"))],
        )
        self.ledger.post_entry(
            "2026-02-01",
            [(self.rent, Decimal("100"), 0), (self.cash, 0, Decimal("100"))],
        )
        self.ledger.post_entry(
            "2026-03-01",
            [(self.draws, Decimal("200"), 0), (self.cash, 0, Decimal("200"))],
        )
        self._assert_balanced(balance_sheet(self.ledger))

    def test_balances_as_of_dates(self):
        self._build_scenario()
        for as_of in ["2026-01-01", "2026-01-31", "2026-02-28", "2026-12-31"]:
            with self.subTest(as_of=as_of):
                self._assert_balanced(balance_sheet(self.ledger, as_of=as_of))

    def test_empty_ledger_balances(self):
        self._assert_balanced(balance_sheet(self.ledger))

    def test_randomized_invariant(self):
        """Post many random balanced entries; the sheet must always balance."""
        rng = random.Random(20260627)
        accounts = [
            self.cash, self.ar, self.ap, self.capital,
            self.draws, self.revenue, self.service, self.rent, self.wages,
        ]
        for n in range(40):
            amount = Decimal(rng.randint(1, 9999)) / Decimal(100)
            debit_acct = rng.choice(accounts)
            credit_acct = rng.choice([a for a in accounts if a != debit_acct])
            day = rng.randint(1, 28)
            month = rng.randint(1, 12)
            date = f"2026-{month:02d}-{day:02d}"
            self.ledger.post_entry(
                date,
                [(debit_acct, amount, 0), (credit_acct, 0, amount)],
            )
        bs = balance_sheet(self.ledger)
        self._assert_balanced(bs)
        # Trial balance must also balance.
        tb = trial_balance(self.ledger)
        self.assertTrue(tb.is_balanced)
        self.assertEqual(tb.total_debit, tb.total_credit)


class CsvExportTest(ReportTestBase):
    def setUp(self):
        super().setUp()
        self._build_scenario()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        for fname in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, fname))
        os.rmdir(self.tmpdir)
        super().tearDown()

    def _read(self, path):
        with open(path, newline="", encoding="utf-8") as handle:
            return list(csv.reader(handle))

    def test_trial_balance_csv_readable(self):
        path = os.path.join(self.tmpdir, "tb.csv")
        export_trial_balance_csv(trial_balance(self.ledger), path)
        rows = self._read(path)
        self.assertEqual(rows[0], ["Code", "Account", "Debit", "Credit"])
        flat = [cell for row in rows for cell in row]
        self.assertIn("TOTAL", flat)
        self.assertIn("True", flat)  # Balanced flag

    def test_income_statement_csv_readable(self):
        path = os.path.join(self.tmpdir, "is.csv")
        export_income_statement_csv(
            income_statement(self.ledger, "2026-01-01", "2026-12-31"), path
        )
        rows = self._read(path)
        flat = [cell for row in rows for cell in row]
        self.assertIn("Net Income", flat)
        self.assertIn("350.00", flat)

    def test_balance_sheet_csv_readable(self):
        path = os.path.join(self.tmpdir, "bs.csv")
        export_balance_sheet_csv(balance_sheet(self.ledger), path)
        rows = self._read(path)
        flat = [cell for row in rows for cell in row]
        self.assertIn("Total Assets", flat)
        self.assertIn(CURRENT_EARNINGS_LABEL, flat)
        self.assertIn("True", flat)  # Balanced flag

    def test_export_creates_nonempty_file(self):
        path = os.path.join(self.tmpdir, "tb.csv")
        export_trial_balance_csv(trial_balance(self.ledger), path)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 0)


if __name__ == "__main__":
    unittest.main()
