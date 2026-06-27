"""Unit tests for ledger.db: schema, default-chart seeding, FK cascade."""

from __future__ import annotations

import unittest

from ledger import db
from ledger.db import DEFAULT_CHART, connect, init_schema, seed_default_chart
from ledger.engine import Ledger
from ledger.models import AccountType


class SchemaTest(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_init_schema_creates_tables(self):
        init_schema(self.conn)
        names = {
            r["name"]
            for r in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn("accounts", names)
        self.assertIn("journal_entries", names)
        self.assertIn("journal_lines", names)

    def test_init_schema_idempotent(self):
        init_schema(self.conn)
        # Insert a row, then call init_schema again; data must survive and no error.
        self.conn.execute(
            "INSERT INTO accounts (code, name, type) VALUES ('1000', 'Cash', 'ASSET')"
        )
        self.conn.commit()
        init_schema(self.conn)  # must not raise or drop data
        count = self.conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()["n"]
        self.assertEqual(count, 1)

    def test_foreign_keys_enabled(self):
        fk = self.conn.execute("PRAGMA foreign_keys").fetchone()[0]
        self.assertEqual(fk, 1)

    def test_account_type_check_constraint(self):
        init_schema(self.conn)
        with self.assertRaises(Exception):
            self.conn.execute(
                "INSERT INTO accounts (code, name, type) VALUES ('9', 'Bad', 'BOGUS')"
            )


class SeedDefaultChartTest(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        init_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_seed_inserts_full_chart(self):
        seed_default_chart(self.conn)
        count = self.conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()["n"]
        self.assertEqual(count, len(DEFAULT_CHART))

    def test_seed_idempotent_not_doubled(self):
        seed_default_chart(self.conn)
        seed_default_chart(self.conn)  # second call must be a no-op
        count = self.conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()["n"]
        self.assertEqual(count, len(DEFAULT_CHART))

    def test_seed_skips_if_any_accounts_exist(self):
        self.conn.execute(
            "INSERT INTO accounts (code, name, type) VALUES ('X', 'Existing', 'ASSET')"
        )
        self.conn.commit()
        seed_default_chart(self.conn)
        count = self.conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()["n"]
        self.assertEqual(count, 1)  # unchanged: seeding was skipped

    def test_seed_accepts_ledger_object(self):
        ledger = Ledger(":memory:")
        seed_default_chart(ledger)  # accepts a Ledger, uses .conn
        self.assertEqual(len(ledger.list_accounts()), len(DEFAULT_CHART))
        ledger.close()

    def test_seeded_codes_and_types_match_chart(self):
        seed_default_chart(self.conn)
        rows = self.conn.execute("SELECT code, name, type FROM accounts").fetchall()
        seeded = {(r["code"], r["name"], r["type"]) for r in rows}
        expected = {(code, name, t.value) for code, name, t in DEFAULT_CHART}
        self.assertEqual(seeded, expected)

    def test_chart_has_all_five_types(self):
        types = {t for _c, _n, t in DEFAULT_CHART}
        self.assertEqual(types, set(AccountType))


class ForeignKeyCascadeTest(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger(":memory:")
        db.seed_default_chart(self.ledger)

    def tearDown(self):
        self.ledger.close()

    def test_cascade_on_entry_delete(self):
        from decimal import Decimal

        cash = self.ledger.get_account_by_code("1000").id
        capital = self.ledger.get_account_by_code("3000").id
        entry = self.ledger.post_entry(
            "2026-01-01",
            [(cash, Decimal("100"), 0), (capital, 0, Decimal("100"))],
        )
        lines = self.ledger.conn.execute(
            "SELECT COUNT(*) AS n FROM journal_lines WHERE entry_id = ?",
            (entry.id,),
        ).fetchone()["n"]
        self.assertEqual(lines, 2)

        # Delete the parent entry directly via SQL to exercise the FK cascade.
        self.ledger.conn.execute(
            "DELETE FROM journal_entries WHERE id = ?", (entry.id,)
        )
        self.ledger.conn.commit()

        lines = self.ledger.conn.execute(
            "SELECT COUNT(*) AS n FROM journal_lines WHERE entry_id = ?",
            (entry.id,),
        ).fetchone()["n"]
        self.assertEqual(lines, 0)

    def test_line_account_fk_blocks_orphan(self):
        from decimal import Decimal

        cash = self.ledger.get_account_by_code("1000").id
        capital = self.ledger.get_account_by_code("3000").id
        self.ledger.post_entry(
            "2026-01-01",
            [(cash, Decimal("100"), 0), (capital, 0, Decimal("100"))],
        )
        # Cash has activity; the FK from journal_lines.account_id must block
        # a raw delete of the referenced account.
        with self.assertRaises(Exception):
            self.ledger.conn.execute("DELETE FROM accounts WHERE id = ?", (cash,))
            self.ledger.conn.commit()


if __name__ == "__main__":
    unittest.main()
