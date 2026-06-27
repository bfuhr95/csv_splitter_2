"""The :class:`Ledger` service API: accounts, posting, balances, and queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date, datetime
from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from . import db
from .models import Account, AccountType, JournalEntry, JournalLine
from .money import ZERO, from_cents, to_cents


class LedgerError(Exception):
    """Raised on any validation or integrity failure in the ledger."""


@dataclass
class LedgerLineRow:
    """One row of an account's general-ledger detail with a running balance."""

    entry_id: int
    date: str
    memo: str
    reference: str
    debit: Decimal
    credit: Decimal
    running_balance: Decimal


def _validate_iso_date(value: str) -> str:
    """Return the value if it is a parseable ISO YYYY-MM-DD date, else raise."""
    try:
        _date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise LedgerError(f"Invalid ISO date: {value!r}") from exc
    return value


class Ledger:
    """Public service layer over the SQLite-backed double-entry ledger."""

    def __init__(self, db_path: str = ":memory:") -> None:
        """Open the database, enforcing foreign keys, and create the schema."""
        self._conn = db.connect(db_path)
        db.init_schema(self._conn)

    @property
    def conn(self):
        """The underlying :class:`sqlite3.Connection`."""
        return self._conn

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()

    # ------------------------------------------------------------------ #
    # Account management
    # ------------------------------------------------------------------ #
    def _row_to_account(self, row) -> Account:
        return Account(
            id=row["id"],
            code=row["code"],
            name=row["name"],
            type=AccountType(row["type"]),
            is_active=bool(row["is_active"]),
        )

    def add_account(self, code: str, name: str, type: AccountType) -> Account:
        """Create a new account. Rejects blank/duplicate code or blank name."""
        code = (code or "").strip()
        name = (name or "").strip()
        if not code:
            raise LedgerError("Account code must not be blank.")
        if not name:
            raise LedgerError("Account name must not be blank.")
        if not isinstance(type, AccountType):
            raise LedgerError("type must be an AccountType.")
        if self.get_account_by_code(code) is not None:
            raise LedgerError(f"Account code already exists: {code!r}")
        cur = self._conn.execute(
            "INSERT INTO accounts (code, name, type, is_active) VALUES (?, ?, ?, 1)",
            (code, name, type.value),
        )
        self._conn.commit()
        return self.get_account(cur.lastrowid)

    def get_account(self, account_id: int) -> Account:
        """Fetch an account by id, raising if it does not exist."""
        row = self._conn.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if row is None:
            raise LedgerError(f"No account with id {account_id}")
        return self._row_to_account(row)

    def get_account_by_code(self, code: str) -> Account | None:
        """Fetch an account by code, or ``None`` if not found."""
        row = self._conn.execute(
            "SELECT * FROM accounts WHERE code = ?", ((code or "").strip(),)
        ).fetchone()
        return self._row_to_account(row) if row else None

    def list_accounts(
        self, active_only: bool = False, type: AccountType | None = None
    ) -> list[Account]:
        """List accounts sorted by code, optionally filtered."""
        sql = "SELECT * FROM accounts"
        clauses: list[str] = []
        params: list[object] = []
        if active_only:
            clauses.append("is_active = 1")
        if type is not None:
            clauses.append("type = ?")
            params.append(type.value)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY code"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_account(r) for r in rows]

    def update_account(
        self,
        account_id: int,
        name: str | None = None,
        code: str | None = None,
        type: AccountType | None = None,
        is_active: bool | None = None,
    ) -> Account:
        """Update mutable fields on an account. Only provided fields change."""
        account = self.get_account(account_id)  # raises if missing
        new_code = account.code if code is None else (code or "").strip()
        new_name = account.name if name is None else (name or "").strip()
        new_type = account.type if type is None else type
        new_active = account.is_active if is_active is None else bool(is_active)

        if not new_code:
            raise LedgerError("Account code must not be blank.")
        if not new_name:
            raise LedgerError("Account name must not be blank.")
        if not isinstance(new_type, AccountType):
            raise LedgerError("type must be an AccountType.")
        if code is not None and new_code != account.code:
            clash = self.get_account_by_code(new_code)
            if clash is not None and clash.id != account_id:
                raise LedgerError(f"Account code already exists: {new_code!r}")

        self._conn.execute(
            "UPDATE accounts SET code = ?, name = ?, type = ?, is_active = ? WHERE id = ?",
            (new_code, new_name, new_type.value, 1 if new_active else 0, account_id),
        )
        self._conn.commit()
        return self.get_account(account_id)

    def account_has_activity(self, account_id: int) -> bool:
        """Return True if any journal line references the account."""
        row = self._conn.execute(
            "SELECT 1 FROM journal_lines WHERE account_id = ? LIMIT 1",
            (account_id,),
        ).fetchone()
        return row is not None

    def deactivate_account(self, account_id: int) -> Account:
        """Mark an account inactive (it is retained for historical entries)."""
        return self.update_account(account_id, is_active=False)

    def delete_account(self, account_id: int) -> None:
        """Delete an account only if no journal line references it."""
        self.get_account(account_id)  # raises if missing
        if self.account_has_activity(account_id):
            raise LedgerError(
                "Cannot delete an account with journal activity; deactivate it instead."
            )
        self._conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        self._conn.commit()

    # ------------------------------------------------------------------ #
    # Journal entries
    # ------------------------------------------------------------------ #
    def _coerce_line(self, raw) -> JournalLine:
        """Normalize a JournalLine / dict / tuple into a JournalLine."""
        if isinstance(raw, JournalLine):
            return JournalLine(
                account_id=raw.account_id,
                debit=raw.debit if isinstance(raw.debit, Decimal) else Decimal(str(raw.debit)),
                credit=raw.credit if isinstance(raw.credit, Decimal) else Decimal(str(raw.credit)),
                line_memo=raw.line_memo or "",
            )
        if isinstance(raw, Mapping):
            return JournalLine(
                account_id=int(raw["account_id"]),
                debit=Decimal(str(raw.get("debit", ZERO))),
                credit=Decimal(str(raw.get("credit", ZERO))),
                line_memo=str(raw.get("line_memo", "")),
            )
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            account_id = int(raw[0])
            debit = Decimal(str(raw[1])) if len(raw) > 1 else ZERO
            credit = Decimal(str(raw[2])) if len(raw) > 2 else ZERO
            line_memo = str(raw[3]) if len(raw) > 3 else ""
            return JournalLine(account_id, debit, credit, line_memo)
        raise LedgerError(f"Unsupported line specification: {raw!r}")

    def post_entry(
        self,
        date: str,
        lines: Iterable,
        memo: str = "",
        reference: str = "",
    ) -> JournalEntry:
        """Validate and atomically persist a balanced journal entry.

        ``lines`` may contain :class:`JournalLine` objects, dicts with keys
        ``account_id``/``debit``/``credit``/``line_memo``, or tuples of
        ``(account_id, debit, credit, line_memo)``.
        """
        _validate_iso_date(date)
        coerced = [self._coerce_line(line) for line in lines]
        if len(coerced) < 2:
            raise LedgerError("A journal entry requires at least two lines.")

        total_debit_cents = 0
        total_credit_cents = 0
        known_account_ids = {a.id for a in self.list_accounts()}

        for index, line in enumerate(coerced, start=1):
            if line.account_id not in known_account_ids:
                raise LedgerError(f"Line {index}: unknown account_id {line.account_id}.")
            debit_cents = to_cents(line.debit)
            credit_cents = to_cents(line.credit)
            if debit_cents < 0 or credit_cents < 0:
                raise LedgerError(f"Line {index}: amounts must be non-negative.")
            if (debit_cents > 0) == (credit_cents > 0):
                raise LedgerError(
                    f"Line {index}: exactly one of debit/credit must be positive."
                )
            total_debit_cents += debit_cents
            total_credit_cents += credit_cents

        if total_debit_cents == 0:
            raise LedgerError("Entry total must be greater than zero.")
        if total_debit_cents != total_credit_cents:
            raise LedgerError(
                "Entry does not balance: debits "
                f"{from_cents(total_debit_cents)} != credits "
                f"{from_cents(total_credit_cents)}."
            )

        created_at = datetime.now().isoformat(timespec="seconds")
        try:
            cur = self._conn.execute(
                "INSERT INTO journal_entries (date, memo, reference, created_at) "
                "VALUES (?, ?, ?, ?)",
                (date, memo or "", reference or "", created_at),
            )
            entry_id = cur.lastrowid
            self._conn.executemany(
                "INSERT INTO journal_lines "
                "(entry_id, account_id, debit, credit, line_memo) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        entry_id,
                        line.account_id,
                        to_cents(line.debit),
                        to_cents(line.credit),
                        line.line_memo or "",
                    )
                    for line in coerced
                ],
            )
            self._conn.commit()
        except Exception as exc:  # pragma: no cover - defensive rollback
            self._conn.rollback()
            raise LedgerError(f"Failed to post entry: {exc}") from exc

        return self.get_entry(entry_id)

    def get_entry(self, entry_id: int) -> JournalEntry:
        """Fetch a journal entry with its lines (incl. account code/name)."""
        head = self._conn.execute(
            "SELECT * FROM journal_entries WHERE id = ?", (entry_id,)
        ).fetchone()
        if head is None:
            raise LedgerError(f"No journal entry with id {entry_id}")
        line_rows = self._conn.execute(
            """
            SELECT jl.*, a.code AS account_code, a.name AS account_name
            FROM journal_lines jl
            JOIN accounts a ON a.id = jl.account_id
            WHERE jl.entry_id = ?
            ORDER BY jl.id
            """,
            (entry_id,),
        ).fetchall()
        lines = [
            JournalLine(
                account_id=r["account_id"],
                debit=from_cents(r["debit"]),
                credit=from_cents(r["credit"]),
                line_memo=r["line_memo"],
                id=r["id"],
                account_code=r["account_code"],
                account_name=r["account_name"],
            )
            for r in line_rows
        ]
        return JournalEntry(
            id=head["id"],
            date=head["date"],
            memo=head["memo"],
            reference=head["reference"],
            lines=lines,
            created_at=head["created_at"],
        )

    def list_entries(
        self, start: str | None = None, end: str | None = None
    ) -> list[JournalEntry]:
        """List journal entries (newest first), optionally within a date range."""
        sql = "SELECT id FROM journal_entries"
        clauses: list[str] = []
        params: list[object] = []
        if start is not None:
            clauses.append("date >= ?")
            params.append(_validate_iso_date(start))
        if end is not None:
            clauses.append("date <= ?")
            params.append(_validate_iso_date(end))
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY date DESC, id DESC"
        ids = [r["id"] for r in self._conn.execute(sql, params).fetchall()]
        return [self.get_entry(i) for i in ids]

    def delete_entry(self, entry_id: int) -> None:
        """Delete a journal entry and its lines (cascade)."""
        self.get_entry(entry_id)  # raises if missing
        self._conn.execute("DELETE FROM journal_entries WHERE id = ?", (entry_id,))
        self._conn.commit()

    # ------------------------------------------------------------------ #
    # Balances and reporting primitives
    # ------------------------------------------------------------------ #
    def raw_balance(self, account_id: int, as_of: str | None = None) -> Decimal:
        """Return debits - credits for an account (cents-exact).

        ``as_of`` is an inclusive upper-bound date filter on the entry date.
        """
        sql = (
            "SELECT COALESCE(SUM(jl.debit), 0) AS d, COALESCE(SUM(jl.credit), 0) AS c "
            "FROM journal_lines jl "
            "JOIN journal_entries je ON je.id = jl.entry_id "
            "WHERE jl.account_id = ?"
        )
        params: list[object] = [account_id]
        if as_of is not None:
            sql += " AND je.date <= ?"
            params.append(_validate_iso_date(as_of))
        row = self._conn.execute(sql, params).fetchone()
        return from_cents(int(row["d"]) - int(row["c"]))

    def account_balance(self, account_id: int, as_of: str | None = None) -> Decimal:
        """Return the normal-side positive balance for an account."""
        account = self.get_account(account_id)
        raw = self.raw_balance(account_id, as_of=as_of)
        return raw if account.type.normal_side == "DEBIT" else -raw

    def ledger_lines(
        self, account_id: int, start: str | None = None, end: str | None = None
    ) -> list[LedgerLineRow]:
        """Return detail rows for one account with a running raw balance.

        The running balance uses the raw debits - credits convention and is
        ordered by entry date then entry id.
        """
        self.get_account(account_id)  # validate existence
        sql = (
            "SELECT je.id AS entry_id, je.date AS date, je.memo AS memo, "
            "je.reference AS reference, jl.debit AS debit, jl.credit AS credit "
            "FROM journal_lines jl "
            "JOIN journal_entries je ON je.id = jl.entry_id "
            "WHERE jl.account_id = ?"
        )
        params: list[object] = [account_id]
        if start is not None:
            sql += " AND je.date >= ?"
            params.append(_validate_iso_date(start))
        if end is not None:
            sql += " AND je.date <= ?"
            params.append(_validate_iso_date(end))
        sql += " ORDER BY je.date, je.id, jl.id"
        rows = self._conn.execute(sql, params).fetchall()

        running_cents = 0
        result: list[LedgerLineRow] = []
        for r in rows:
            running_cents += int(r["debit"]) - int(r["credit"])
            result.append(
                LedgerLineRow(
                    entry_id=r["entry_id"],
                    date=r["date"],
                    memo=r["memo"],
                    reference=r["reference"],
                    debit=from_cents(int(r["debit"])),
                    credit=from_cents(int(r["credit"])),
                    running_balance=from_cents(running_cents),
                )
            )
        return result

    def totals_by_type(self, as_of: str | None = None) -> dict[AccountType, Decimal]:
        """Return summed normal-side account balances grouped by account type."""
        totals: dict[AccountType, Decimal] = {t: ZERO for t in AccountType}
        for account in self.list_accounts():
            totals[account.type] += self.account_balance(account.id, as_of=as_of)
        return totals
