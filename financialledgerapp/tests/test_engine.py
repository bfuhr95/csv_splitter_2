"""Unit tests for ledger.engine.Ledger: accounts, posting, balances, queries."""

from __future__ import annotations

import unittest
from decimal import Decimal

from ledger import db
from ledger.engine import Ledger, LedgerError, LedgerLineRow
from ledger.models import AccountType
from ledger.money import ZERO


class LedgerTestBase(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger(":memory:")

    def tearDown(self):
        self.ledger.close()

    def _seed(self):
        """Seed the default chart and stash common account ids."""
        db.seed_default_chart(self.ledger)
        self.cash = self.ledger.get_account_by_code("1000").id
        self.ar = self.ledger.get_account_by_code("1100").id
        self.ap = self.ledger.get_account_by_code("2000").id
        self.capital = self.ledger.get_account_by_code("3000").id
        self.draws = self.ledger.get_account_by_code("3100").id
        self.revenue = self.ledger.get_account_by_code("4000").id
        self.rent = self.ledger.get_account_by_code("5100").id


class AddAccountTest(LedgerTestBase):
    def test_add_account_returns_account_with_id(self):
        acct = self.ledger.add_account("1000", "Cash", AccountType.ASSET)
        self.assertIsNotNone(acct.id)
        self.assertEqual(acct.code, "1000")
        self.assertEqual(acct.name, "Cash")
        self.assertEqual(acct.type, AccountType.ASSET)
        self.assertTrue(acct.is_active)

    def test_duplicate_code_rejected(self):
        self.ledger.add_account("1000", "Cash", AccountType.ASSET)
        with self.assertRaises(LedgerError):
            self.ledger.add_account("1000", "Other", AccountType.ASSET)

    def test_blank_code_rejected(self):
        with self.assertRaises(LedgerError):
            self.ledger.add_account("   ", "Cash", AccountType.ASSET)
        with self.assertRaises(LedgerError):
            self.ledger.add_account("", "Cash", AccountType.ASSET)

    def test_blank_name_rejected(self):
        with self.assertRaises(LedgerError):
            self.ledger.add_account("1000", "  ", AccountType.ASSET)

    def test_non_accounttype_rejected(self):
        with self.assertRaises(LedgerError):
            self.ledger.add_account("1000", "Cash", "ASSET")

    def test_code_and_name_are_stripped(self):
        acct = self.ledger.add_account("  1000  ", "  Cash  ", AccountType.ASSET)
        self.assertEqual(acct.code, "1000")
        self.assertEqual(acct.name, "Cash")


class ListAndGetAccountTest(LedgerTestBase):
    def test_list_sorted_by_code(self):
        self._seed()
        codes = [a.code for a in self.ledger.list_accounts()]
        self.assertEqual(codes, sorted(codes))

    def test_get_account_missing_raises(self):
        with self.assertRaises(LedgerError):
            self.ledger.get_account(99999)

    def test_get_account_by_code_missing_returns_none(self):
        self.assertIsNone(self.ledger.get_account_by_code("9999"))

    def test_filter_by_type(self):
        self._seed()
        assets = self.ledger.list_accounts(type=AccountType.ASSET)
        self.assertTrue(all(a.type == AccountType.ASSET for a in assets))
        self.assertEqual(len(assets), 4)

    def test_filter_active_only(self):
        self._seed()
        self.ledger.deactivate_account(self.cash)
        active = self.ledger.list_accounts(active_only=True)
        self.assertNotIn(self.cash, [a.id for a in active])


class PostEntryValidationTest(LedgerTestBase):
    def setUp(self):
        super().setUp()
        self._seed()

    def test_balanced_two_line_entry_accepted(self):
        entry = self.ledger.post_entry(
            "2026-01-01",
            [(self.cash, Decimal("100"), 0), (self.capital, 0, Decimal("100"))],
            memo="invest",
            reference="JE-1",
        )
        self.assertIsNotNone(entry.id)
        self.assertEqual(len(entry.lines), 2)
        self.assertEqual(entry.memo, "invest")
        self.assertEqual(entry.reference, "JE-1")
        self.assertIsNotNone(entry.created_at)

    def test_balanced_multi_line_entry_accepted(self):
        entry = self.ledger.post_entry(
            "2026-01-01",
            [
                (self.cash, Decimal("60"), 0),
                (self.ar, Decimal("40"), 0),
                (self.revenue, 0, Decimal("100")),
            ],
        )
        self.assertEqual(len(entry.lines), 3)

    def test_unbalanced_rejected(self):
        with self.assertRaises(LedgerError):
            self.ledger.post_entry(
                "2026-01-01",
                [(self.cash, Decimal("100"), 0), (self.capital, 0, Decimal("99"))],
            )

    def test_single_line_rejected(self):
        with self.assertRaises(LedgerError):
            self.ledger.post_entry(
                "2026-01-01", [(self.cash, Decimal("100"), 0)]
            )

    def test_negative_amount_rejected(self):
        with self.assertRaises(LedgerError):
            self.ledger.post_entry(
                "2026-01-01",
                [(self.cash, Decimal("-100"), 0), (self.capital, 0, Decimal("-100"))],
            )

    def test_both_sides_set_rejected(self):
        with self.assertRaises(LedgerError):
            self.ledger.post_entry(
                "2026-01-01",
                [
                    (self.cash, Decimal("100"), Decimal("100")),
                    (self.capital, 0, Decimal("100")),
                ],
            )

    def test_line_with_neither_side_rejected(self):
        with self.assertRaises(LedgerError):
            self.ledger.post_entry(
                "2026-01-01",
                [(self.cash, 0, 0), (self.capital, 0, Decimal("100"))],
            )

    def test_zero_total_rejected(self):
        # Every line has neither side positive -> caught as line error first,
        # but a genuinely zero-total set is rejected.
        with self.assertRaises(LedgerError):
            self.ledger.post_entry(
                "2026-01-01",
                [(self.cash, 0, 0), (self.capital, 0, 0)],
            )

    def test_unknown_account_rejected(self):
        with self.assertRaises(LedgerError):
            self.ledger.post_entry(
                "2026-01-01",
                [(99999, Decimal("100"), 0), (self.capital, 0, Decimal("100"))],
            )

    def test_invalid_date_rejected(self):
        with self.assertRaises(LedgerError):
            self.ledger.post_entry(
                "01/01/2026",
                [(self.cash, Decimal("100"), 0), (self.capital, 0, Decimal("100"))],
            )

    def test_accepts_dict_lines(self):
        entry = self.ledger.post_entry(
            "2026-01-01",
            [
                {"account_id": self.cash, "debit": "100"},
                {"account_id": self.capital, "credit": "100"},
            ],
        )
        self.assertEqual(len(entry.lines), 2)

    def test_accepts_journalline_objects(self):
        from ledger.models import JournalLine

        entry = self.ledger.post_entry(
            "2026-01-01",
            [
                JournalLine(account_id=self.cash, debit=Decimal("100")),
                JournalLine(account_id=self.capital, credit=Decimal("100")),
            ],
        )
        self.assertEqual(len(entry.lines), 2)

    def test_cents_exact_balance_required(self):
        # Off by one cent must be rejected.
        with self.assertRaises(LedgerError):
            self.ledger.post_entry(
                "2026-01-01",
                [
                    (self.cash, Decimal("100.01"), 0),
                    (self.capital, 0, Decimal("100.00")),
                ],
            )

    def test_failed_entry_does_not_persist(self):
        before = len(self.ledger.list_entries())
        with self.assertRaises(LedgerError):
            self.ledger.post_entry(
                "2026-01-01",
                [(self.cash, Decimal("100"), 0), (self.capital, 0, Decimal("99"))],
            )
        self.assertEqual(len(self.ledger.list_entries()), before)


class BalanceSignTest(LedgerTestBase):
    """Verify raw_balance and account_balance signs for each AccountType."""

    def setUp(self):
        super().setUp()
        self._seed()

    def test_asset_debit_normal_positive(self):
        self.ledger.post_entry(
            "2026-01-01",
            [(self.cash, Decimal("100"), 0), (self.capital, 0, Decimal("100"))],
        )
        # ASSET normal side is DEBIT: raw and account balance both positive.
        self.assertEqual(self.ledger.raw_balance(self.cash), Decimal("100.00"))
        self.assertEqual(self.ledger.account_balance(self.cash), Decimal("100.00"))

    def test_liability_credit_normal_positive(self):
        self.ledger.post_entry(
            "2026-01-01",
            [(self.rent, Decimal("100"), 0), (self.ap, 0, Decimal("100"))],
        )
        # LIABILITY raw is negative (credit), but normal-side balance positive.
        self.assertEqual(self.ledger.raw_balance(self.ap), Decimal("-100.00"))
        self.assertEqual(self.ledger.account_balance(self.ap), Decimal("100.00"))

    def test_equity_credit_normal_positive(self):
        self.ledger.post_entry(
            "2026-01-01",
            [(self.cash, Decimal("100"), 0), (self.capital, 0, Decimal("100"))],
        )
        self.assertEqual(self.ledger.raw_balance(self.capital), Decimal("-100.00"))
        self.assertEqual(self.ledger.account_balance(self.capital), Decimal("100.00"))

    def test_revenue_credit_normal_positive(self):
        self.ledger.post_entry(
            "2026-01-01",
            [(self.cash, Decimal("250"), 0), (self.revenue, 0, Decimal("250"))],
        )
        self.assertEqual(self.ledger.raw_balance(self.revenue), Decimal("-250.00"))
        self.assertEqual(self.ledger.account_balance(self.revenue), Decimal("250.00"))

    def test_expense_debit_normal_positive(self):
        self.ledger.post_entry(
            "2026-01-01",
            [(self.rent, Decimal("75"), 0), (self.cash, 0, Decimal("75"))],
        )
        self.assertEqual(self.ledger.raw_balance(self.rent), Decimal("75.00"))
        self.assertEqual(self.ledger.account_balance(self.rent), Decimal("75.00"))

    def test_contra_equity_draws_negative(self):
        # A debit to an EQUITY account (owner draws) yields negative balance.
        self.ledger.post_entry(
            "2026-01-01",
            [(self.draws, Decimal("50"), 0), (self.cash, 0, Decimal("50"))],
        )
        self.assertEqual(self.ledger.account_balance(self.draws), Decimal("-50.00"))


class LedgerLinesTest(LedgerTestBase):
    def setUp(self):
        super().setUp()
        self._seed()

    def test_running_balance_and_ordering(self):
        self.ledger.post_entry(
            "2026-01-01",
            [(self.cash, Decimal("1000"), 0), (self.capital, 0, Decimal("1000"))],
        )
        self.ledger.post_entry(
            "2026-01-05",
            [(self.cash, Decimal("300"), 0), (self.revenue, 0, Decimal("300"))],
        )
        self.ledger.post_entry(
            "2026-02-10",
            [(self.draws, Decimal("50"), 0), (self.cash, 0, Decimal("50"))],
        )
        rows = self.ledger.ledger_lines(self.cash)
        self.assertEqual([r.date for r in rows], ["2026-01-01", "2026-01-05", "2026-02-10"])
        self.assertEqual([r.running_balance for r in rows],
                         [Decimal("1000.00"), Decimal("1300.00"), Decimal("1250.00")])
        self.assertIsInstance(rows[0], LedgerLineRow)
        self.assertEqual(rows[0].debit, Decimal("1000.00"))
        self.assertEqual(rows[2].credit, Decimal("50.00"))

    def test_ordering_independent_of_insertion_order(self):
        # Insert a later-dated entry first; ledger_lines must still order by date.
        self.ledger.post_entry(
            "2026-03-01",
            [(self.cash, Decimal("200"), 0), (self.revenue, 0, Decimal("200"))],
        )
        self.ledger.post_entry(
            "2026-01-01",
            [(self.cash, Decimal("100"), 0), (self.capital, 0, Decimal("100"))],
        )
        rows = self.ledger.ledger_lines(self.cash)
        self.assertEqual([r.date for r in rows], ["2026-01-01", "2026-03-01"])
        self.assertEqual([r.running_balance for r in rows],
                         [Decimal("100.00"), Decimal("300.00")])

    def test_date_range_filter(self):
        self.ledger.post_entry(
            "2026-01-01",
            [(self.cash, Decimal("100"), 0), (self.capital, 0, Decimal("100"))],
        )
        self.ledger.post_entry(
            "2026-06-01",
            [(self.cash, Decimal("50"), 0), (self.revenue, 0, Decimal("50"))],
        )
        rows = self.ledger.ledger_lines(self.cash, start="2026-05-01", end="2026-12-31")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].date, "2026-06-01")

    def test_empty_for_account_without_activity(self):
        self.assertEqual(self.ledger.ledger_lines(self.cash), [])

    def test_unknown_account_raises(self):
        with self.assertRaises(LedgerError):
            self.ledger.ledger_lines(99999)


class AsOfFilterTest(LedgerTestBase):
    def setUp(self):
        super().setUp()
        self._seed()

    def test_as_of_inclusive_upper_bound(self):
        self.ledger.post_entry(
            "2026-01-15",
            [(self.cash, Decimal("100"), 0), (self.capital, 0, Decimal("100"))],
        )
        self.ledger.post_entry(
            "2026-02-15",
            [(self.cash, Decimal("200"), 0), (self.revenue, 0, Decimal("200"))],
        )
        # Inclusive on the boundary date.
        self.assertEqual(self.ledger.account_balance(self.cash, as_of="2026-01-15"),
                         Decimal("100.00"))
        self.assertEqual(self.ledger.account_balance(self.cash, as_of="2026-02-15"),
                         Decimal("300.00"))
        # Before any entries.
        self.assertEqual(self.ledger.account_balance(self.cash, as_of="2025-12-31"),
                         ZERO)

    def test_totals_by_type(self):
        self.ledger.post_entry(
            "2026-01-01",
            [(self.cash, Decimal("100"), 0), (self.capital, 0, Decimal("100"))],
        )
        totals = self.ledger.totals_by_type()
        self.assertEqual(totals[AccountType.ASSET], Decimal("100.00"))
        self.assertEqual(totals[AccountType.EQUITY], Decimal("100.00"))
        self.assertEqual(totals[AccountType.REVENUE], ZERO)


class DeleteEntryTest(LedgerTestBase):
    def setUp(self):
        super().setUp()
        self._seed()

    def test_delete_entry_cascades_lines_and_updates_balances(self):
        entry = self.ledger.post_entry(
            "2026-01-01",
            [(self.cash, Decimal("100"), 0), (self.capital, 0, Decimal("100"))],
        )
        self.assertEqual(self.ledger.account_balance(self.cash), Decimal("100.00"))
        # Confirm lines exist before delete.
        line_count = self.ledger.conn.execute(
            "SELECT COUNT(*) AS n FROM journal_lines WHERE entry_id = ?",
            (entry.id,),
        ).fetchone()["n"]
        self.assertEqual(line_count, 2)

        self.ledger.delete_entry(entry.id)

        # Lines cascaded away.
        line_count = self.ledger.conn.execute(
            "SELECT COUNT(*) AS n FROM journal_lines WHERE entry_id = ?",
            (entry.id,),
        ).fetchone()["n"]
        self.assertEqual(line_count, 0)
        # Balance reverts to zero.
        self.assertEqual(self.ledger.account_balance(self.cash), ZERO)

    def test_delete_missing_entry_raises(self):
        with self.assertRaises(LedgerError):
            self.ledger.delete_entry(99999)


class DeleteAccountTest(LedgerTestBase):
    def setUp(self):
        super().setUp()
        self._seed()

    def test_delete_account_with_activity_guarded(self):
        self.ledger.post_entry(
            "2026-01-01",
            [(self.cash, Decimal("100"), 0), (self.capital, 0, Decimal("100"))],
        )
        self.assertTrue(self.ledger.account_has_activity(self.cash))
        with self.assertRaises(LedgerError):
            self.ledger.delete_account(self.cash)
        # Account still present.
        self.assertIsNotNone(self.ledger.get_account(self.cash))

    def test_delete_unused_account_succeeds(self):
        unused = self.ledger.add_account("9999", "Scratch", AccountType.ASSET).id
        self.assertFalse(self.ledger.account_has_activity(unused))
        self.ledger.delete_account(unused)
        with self.assertRaises(LedgerError):
            self.ledger.get_account(unused)

    def test_deactivate_keeps_account(self):
        acct = self.ledger.deactivate_account(self.cash)
        self.assertFalse(acct.is_active)
        self.assertIsNotNone(self.ledger.get_account(self.cash))


class ListEntriesTest(LedgerTestBase):
    def setUp(self):
        super().setUp()
        self._seed()

    def test_newest_first(self):
        self.ledger.post_entry(
            "2026-01-01",
            [(self.cash, Decimal("100"), 0), (self.capital, 0, Decimal("100"))],
        )
        self.ledger.post_entry(
            "2026-03-01",
            [(self.cash, Decimal("50"), 0), (self.revenue, 0, Decimal("50"))],
        )
        entries = self.ledger.list_entries()
        self.assertEqual([e.date for e in entries], ["2026-03-01", "2026-01-01"])

    def test_date_range(self):
        self.ledger.post_entry(
            "2026-01-01",
            [(self.cash, Decimal("100"), 0), (self.capital, 0, Decimal("100"))],
        )
        self.ledger.post_entry(
            "2026-06-01",
            [(self.cash, Decimal("50"), 0), (self.revenue, 0, Decimal("50"))],
        )
        entries = self.ledger.list_entries(start="2026-05-01")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].date, "2026-06-01")

    def test_get_entry_has_account_code_and_name(self):
        entry = self.ledger.post_entry(
            "2026-01-01",
            [(self.cash, Decimal("100"), 0), (self.capital, 0, Decimal("100"))],
        )
        fetched = self.ledger.get_entry(entry.id)
        codes = {line.account_code for line in fetched.lines}
        self.assertEqual(codes, {"1000", "3000"})
        self.assertTrue(all(line.account_name for line in fetched.lines))


if __name__ == "__main__":
    unittest.main()
