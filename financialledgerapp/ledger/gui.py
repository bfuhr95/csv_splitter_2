"""Tkinter desktop GUI for the double-entry accounting ledger."""

from __future__ import annotations

from datetime import date as _date
from decimal import Decimal, InvalidOperation
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import reports
from .db import seed_default_chart
from .engine import Ledger, LedgerError
from .models import Account, AccountType
from .money import ZERO, fmt, parse_money

LARGE_FONT = ("Arial", 12)


def _today() -> str:
    """Return today's date as an ISO string."""
    return _date.today().isoformat()


class AccountDialog(tk.Toplevel):
    """Modal dialog for creating or editing an account."""

    def __init__(self, parent, title: str, account: Account | None = None) -> None:
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.resizable(False, False)
        self.result: dict | None = None

        # NB: these StringVar/BooleanVar attributes are deliberately *not* named
        # ``_name``/``_code``/etc. Tkinter's ``BaseWidget`` stores the widget's
        # Tk pathname in ``self._name``; shadowing it with a StringVar breaks
        # ``destroy()`` (``unhashable type: 'StringVar'``). Use ``_var_*`` names.
        self._var_code = tk.StringVar(value=account.code if account else "")
        self._var_name = tk.StringVar(value=account.name if account else "")
        self._var_type = tk.StringVar(
            value=(account.type.value if account else AccountType.ASSET.value)
        )
        self._var_active = tk.BooleanVar(value=account.is_active if account else True)

        body = ttk.Frame(self, padding=12)
        body.grid(row=0, column=0, sticky="nsew")
        ttk.Label(body, text="Code:").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(body, textvariable=self._var_code, width=24).grid(
            row=0, column=1, pady=4
        )
        ttk.Label(body, text="Name:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(body, textvariable=self._var_name, width=24).grid(
            row=1, column=1, pady=4
        )
        ttk.Label(body, text="Type:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Combobox(
            body,
            textvariable=self._var_type,
            values=[t.value for t in AccountType],
            state="readonly",
            width=21,
        ).grid(row=2, column=1, pady=4)
        ttk.Checkbutton(body, text="Active", variable=self._var_active).grid(
            row=3, column=1, sticky="w", pady=4
        )

        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(buttons, text="OK", command=self._on_ok).grid(row=0, column=0, padx=4)
        ttk.Button(buttons, text="Cancel", command=self._on_cancel).grid(
            row=0, column=1, padx=4
        )

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Return>", lambda _e: self._on_ok())
        self.bind("<Escape>", lambda _e: self._on_cancel())

    def _on_ok(self) -> None:
        self.result = {
            "code": self._var_code.get().strip(),
            "name": self._var_name.get().strip(),
            "type": AccountType(self._var_type.get()),
            "is_active": bool(self._var_active.get()),
        }
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()


class LedgerApp(tk.Tk):
    """Main application window with notebook tabs for the ledger."""

    def __init__(self, db_path: str = "ledger.db") -> None:
        super().__init__()
        self.db_path = db_path
        self.ledger = Ledger(db_path)
        self.title("Double-Entry Ledger")
        self.geometry("1100x720")

        self._build_menubar()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_accounts_tab()
        self._build_journal_tab()
        self._build_general_ledger_tab()
        self._build_reports_tab()

        self.refresh_all()

    # ------------------------------------------------------------------ #
    # Menubar
    # ------------------------------------------------------------------ #
    def _build_menubar(self) -> None:
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New Company...", command=self._menu_new_company)
        file_menu.add_command(label="Open .db...", command=self._menu_open_db)
        file_menu.add_command(label="Load Sample Data", command=self._menu_load_sample)
        file_menu.add_separator()
        file_menu.add_command(label="Export...", command=self._menu_export)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self._menu_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

    def _menu_new_company(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".db", filetypes=[("SQLite DB", "*.db")]
        )
        if path:
            self._switch_db(path)

    def _menu_open_db(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("SQLite DB", "*.db")])
        if path:
            self._switch_db(path)

    def _switch_db(self, path: str) -> None:
        try:
            self.ledger.close()
            self.ledger = Ledger(path)
            self.db_path = path
            self.title(f"Double-Entry Ledger - {path}")
            self.refresh_all()
        except Exception as exc:  # pragma: no cover - GUI guard
            messagebox.showerror("Open failed", str(exc))

    def _menu_load_sample(self) -> None:
        seed_default_chart(self.ledger)
        self.refresh_all()
        messagebox.showinfo("Sample Data", "Default chart of accounts loaded.")

    def _menu_export(self) -> None:
        self.notebook.select(3)

    def _menu_about(self) -> None:
        messagebox.showinfo(
            "About",
            "Double-Entry Ledger\nStandard-library Python + tkinter.\n"
            "A simple, balancing financial accounting ledger.",
        )

    # ------------------------------------------------------------------ #
    # Chart of Accounts tab
    # ------------------------------------------------------------------ #
    def _build_accounts_tab(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Chart of Accounts")

        columns = ("code", "name", "type", "active", "balance")
        self.acct_tree = ttk.Treeview(tab, columns=columns, show="headings", height=18)
        for col, heading, width, anchor in (
            ("code", "Code", 80, "w"),
            ("name", "Name", 280, "w"),
            ("type", "Type", 120, "w"),
            ("active", "Active", 80, "center"),
            ("balance", "Balance", 140, "e"),
        ):
            self.acct_tree.heading(col, text=heading)
            self.acct_tree.column(col, width=width, anchor=anchor)
        self.acct_tree.pack(fill="both", expand=True, side="top", padx=6, pady=6)

        buttons = ttk.Frame(tab)
        buttons.pack(fill="x", padx=6, pady=6)
        ttk.Button(buttons, text="New", command=self._account_new).pack(side="left", padx=4)
        ttk.Button(buttons, text="Edit", command=self._account_edit).pack(side="left", padx=4)
        ttk.Button(
            buttons, text="Activate-Toggle", command=self._account_toggle
        ).pack(side="left", padx=4)
        ttk.Button(buttons, text="Delete", command=self._account_delete).pack(
            side="left", padx=4
        )

    def _selected_account_id(self) -> int | None:
        sel = self.acct_tree.selection()
        if not sel:
            return None
        return int(sel[0])

    def refresh_accounts(self) -> None:
        self.acct_tree.delete(*self.acct_tree.get_children())
        for account in self.ledger.list_accounts():
            balance = self.ledger.account_balance(account.id)
            self.acct_tree.insert(
                "",
                "end",
                iid=str(account.id),
                values=(
                    account.code,
                    account.name,
                    account.type.value,
                    "Yes" if account.is_active else "No",
                    fmt(balance),
                ),
            )

    def _account_new(self) -> None:
        dialog = AccountDialog(self, "New Account")
        self.wait_window(dialog)
        if dialog.result is None:
            return
        try:
            self.ledger.add_account(
                dialog.result["code"], dialog.result["name"], dialog.result["type"]
            )
            self.refresh_all()
        except LedgerError as exc:
            messagebox.showerror("Cannot add account", str(exc))

    def _account_edit(self) -> None:
        account_id = self._selected_account_id()
        if account_id is None:
            messagebox.showinfo("Edit", "Select an account first.")
            return
        account = self.ledger.get_account(account_id)
        dialog = AccountDialog(self, "Edit Account", account)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        try:
            self.ledger.update_account(
                account_id,
                name=dialog.result["name"],
                code=dialog.result["code"],
                type=dialog.result["type"],
                is_active=dialog.result["is_active"],
            )
            self.refresh_all()
        except LedgerError as exc:
            messagebox.showerror("Cannot update account", str(exc))

    def _account_toggle(self) -> None:
        account_id = self._selected_account_id()
        if account_id is None:
            messagebox.showinfo("Toggle", "Select an account first.")
            return
        account = self.ledger.get_account(account_id)
        try:
            self.ledger.update_account(account_id, is_active=not account.is_active)
            self.refresh_all()
        except LedgerError as exc:
            messagebox.showerror("Cannot toggle account", str(exc))

    def _account_delete(self) -> None:
        account_id = self._selected_account_id()
        if account_id is None:
            messagebox.showinfo("Delete", "Select an account first.")
            return
        try:
            self.ledger.delete_account(account_id)
            self.refresh_all()
        except LedgerError as exc:
            messagebox.showerror("Cannot delete account", str(exc))

    # ------------------------------------------------------------------ #
    # Journal Entry tab
    # ------------------------------------------------------------------ #
    def _build_journal_tab(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Journal Entry")

        header = ttk.Frame(tab)
        header.pack(fill="x", padx=6, pady=6)
        ttk.Label(header, text="Date:").grid(row=0, column=0, sticky="w", padx=4)
        self.je_date = tk.StringVar(value=_today())
        ttk.Entry(header, textvariable=self.je_date, width=14).grid(row=0, column=1, padx=4)
        ttk.Label(header, text="Memo:").grid(row=0, column=2, sticky="w", padx=4)
        self.je_memo = tk.StringVar()
        ttk.Entry(header, textvariable=self.je_memo, width=36).grid(row=0, column=3, padx=4)
        ttk.Label(header, text="Reference:").grid(row=0, column=4, sticky="w", padx=4)
        self.je_reference = tk.StringVar()
        ttk.Entry(header, textvariable=self.je_reference, width=18).grid(
            row=0, column=5, padx=4
        )

        # Lines grid.
        self.lines_frame = ttk.LabelFrame(tab, text="Lines")
        self.lines_frame.pack(fill="x", padx=6, pady=6)
        grid_head = ttk.Frame(self.lines_frame)
        grid_head.pack(fill="x")
        for text, width in (("Account", 36), ("Debit", 14), ("Credit", 14), ("Memo", 28)):
            ttk.Label(grid_head, text=text, width=width).pack(side="left", padx=4)

        self.lines_container = ttk.Frame(self.lines_frame)
        self.lines_container.pack(fill="x")
        self.je_line_rows: list[dict] = []

        line_buttons = ttk.Frame(tab)
        line_buttons.pack(fill="x", padx=6, pady=4)
        ttk.Button(line_buttons, text="Add Line", command=self._je_add_line).pack(
            side="left", padx=4
        )
        ttk.Button(line_buttons, text="Remove Line", command=self._je_remove_line).pack(
            side="left", padx=4
        )

        totals = ttk.Frame(tab)
        totals.pack(fill="x", padx=6, pady=4)
        self.je_total_debit = tk.StringVar(value=fmt(ZERO))
        self.je_total_credit = tk.StringVar(value=fmt(ZERO))
        self.je_balance_status = tk.StringVar(value="Balanced")
        ttk.Label(totals, text="Total Debit:").pack(side="left", padx=4)
        ttk.Label(totals, textvariable=self.je_total_debit).pack(side="left", padx=4)
        ttk.Label(totals, text="Total Credit:").pack(side="left", padx=4)
        ttk.Label(totals, textvariable=self.je_total_credit).pack(side="left", padx=4)
        self.je_status_label = ttk.Label(totals, textvariable=self.je_balance_status)
        self.je_status_label.pack(side="left", padx=12)

        ttk.Button(tab, text="Post Entry", command=self._je_post).pack(
            anchor="w", padx=6, pady=4
        )

        # Recent entries.
        recent = ttk.LabelFrame(tab, text="Recent Entries")
        recent.pack(fill="both", expand=True, padx=6, pady=6)
        cols = ("date", "memo", "reference", "amount")
        self.je_tree = ttk.Treeview(recent, columns=cols, show="headings", height=8)
        for col, heading, width, anchor in (
            ("date", "Date", 100, "w"),
            ("memo", "Memo", 320, "w"),
            ("reference", "Reference", 140, "w"),
            ("amount", "Amount", 120, "e"),
        ):
            self.je_tree.heading(col, text=heading)
            self.je_tree.column(col, width=width, anchor=anchor)
        self.je_tree.pack(fill="both", expand=True, side="top")
        ttk.Button(recent, text="Delete Selected", command=self._je_delete).pack(
            anchor="w", pady=4
        )

        # Seed two starting lines.
        self._je_add_line()
        self._je_add_line()

    def _account_choices(self) -> list[str]:
        return [
            f"{a.code} - {a.name}"
            for a in self.ledger.list_accounts(active_only=True)
        ]

    def _account_id_from_choice(self, choice: str) -> int | None:
        if not choice:
            return None
        code = choice.split(" - ", 1)[0].strip()
        account = self.ledger.get_account_by_code(code)
        return account.id if account else None

    def _je_add_line(self) -> None:
        row_frame = ttk.Frame(self.lines_container)
        row_frame.pack(fill="x", pady=2)
        account_var = tk.StringVar()
        debit_var = tk.StringVar()
        credit_var = tk.StringVar()
        memo_var = tk.StringVar()

        combo = ttk.Combobox(
            row_frame,
            textvariable=account_var,
            values=self._account_choices(),
            state="readonly",
            width=34,
        )
        combo.pack(side="left", padx=4)
        debit_entry = ttk.Entry(row_frame, textvariable=debit_var, width=14)
        debit_entry.pack(side="left", padx=4)
        credit_entry = ttk.Entry(row_frame, textvariable=credit_var, width=14)
        credit_entry.pack(side="left", padx=4)
        ttk.Entry(row_frame, textvariable=memo_var, width=28).pack(side="left", padx=4)

        debit_var.trace_add("write", lambda *_: self._je_update_totals())
        credit_var.trace_add("write", lambda *_: self._je_update_totals())

        self.je_line_rows.append(
            {
                "frame": row_frame,
                "account": account_var,
                "debit": debit_var,
                "credit": credit_var,
                "memo": memo_var,
                "combo": combo,
            }
        )
        self._je_update_totals()

    def _je_remove_line(self) -> None:
        if not self.je_line_rows:
            return
        row = self.je_line_rows.pop()
        row["frame"].destroy()
        self._je_update_totals()

    def _je_update_totals(self) -> None:
        total_debit = ZERO
        total_credit = ZERO
        for row in self.je_line_rows:
            try:
                total_debit += parse_money(row["debit"].get())
            except (InvalidOperation, ValueError):
                pass
            try:
                total_credit += parse_money(row["credit"].get())
            except (InvalidOperation, ValueError):
                pass
        self.je_total_debit.set(fmt(total_debit))
        self.je_total_credit.set(fmt(total_credit))
        if total_debit == total_credit and total_debit > ZERO:
            self.je_balance_status.set("Balanced")
            self.je_status_label.configure(foreground="green")
        else:
            diff = total_debit - total_credit
            self.je_balance_status.set(f"Out of balance: {fmt(diff)}")
            self.je_status_label.configure(foreground="red")

    def _je_post(self) -> None:
        lines = []
        for row in self.je_line_rows:
            account_id = self._account_id_from_choice(row["account"].get())
            if account_id is None:
                continue
            debit = parse_money(row["debit"].get())
            credit = parse_money(row["credit"].get())
            if debit == ZERO and credit == ZERO:
                continue
            lines.append(
                {
                    "account_id": account_id,
                    "debit": debit,
                    "credit": credit,
                    "line_memo": row["memo"].get(),
                }
            )
        try:
            self.ledger.post_entry(
                self.je_date.get(),
                lines,
                memo=self.je_memo.get(),
                reference=self.je_reference.get(),
            )
        except LedgerError as exc:
            messagebox.showerror("Cannot post entry", str(exc))
            return
        # Clear inputs on success.
        self.je_memo.set("")
        self.je_reference.set("")
        for row in list(self.je_line_rows):
            row["frame"].destroy()
        self.je_line_rows.clear()
        self._je_add_line()
        self._je_add_line()
        self.refresh_all()

    def refresh_journal(self) -> None:
        # Refresh account dropdowns for any existing rows.
        choices = self._account_choices()
        for row in self.je_line_rows:
            row["combo"].configure(values=choices)
        self.je_tree.delete(*self.je_tree.get_children())
        for entry in self.ledger.list_entries():
            amount = sum((line.debit for line in entry.lines), ZERO)
            self.je_tree.insert(
                "",
                "end",
                iid=str(entry.id),
                values=(entry.date, entry.memo, entry.reference, fmt(amount)),
            )

    def _je_delete(self) -> None:
        sel = self.je_tree.selection()
        if not sel:
            messagebox.showinfo("Delete", "Select an entry first.")
            return
        try:
            self.ledger.delete_entry(int(sel[0]))
            self.refresh_all()
        except LedgerError as exc:
            messagebox.showerror("Cannot delete entry", str(exc))

    # ------------------------------------------------------------------ #
    # General Ledger tab
    # ------------------------------------------------------------------ #
    def _build_general_ledger_tab(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="General Ledger")

        controls = ttk.Frame(tab)
        controls.pack(fill="x", padx=6, pady=6)
        ttk.Label(controls, text="Account:").pack(side="left", padx=4)
        self.gl_account = tk.StringVar()
        self.gl_combo = ttk.Combobox(
            controls, textvariable=self.gl_account, state="readonly", width=34
        )
        self.gl_combo.pack(side="left", padx=4)
        ttk.Label(controls, text="Start:").pack(side="left", padx=4)
        self.gl_start = tk.StringVar()
        ttk.Entry(controls, textvariable=self.gl_start, width=12).pack(side="left", padx=4)
        ttk.Label(controls, text="End:").pack(side="left", padx=4)
        self.gl_end = tk.StringVar()
        ttk.Entry(controls, textvariable=self.gl_end, width=12).pack(side="left", padx=4)
        ttk.Button(controls, text="Show", command=self._gl_show).pack(side="left", padx=8)

        cols = ("date", "memo", "reference", "debit", "credit", "running")
        self.gl_tree = ttk.Treeview(tab, columns=cols, show="headings", height=18)
        for col, heading, width, anchor in (
            ("date", "Date", 100, "w"),
            ("memo", "Memo", 280, "w"),
            ("reference", "Reference", 140, "w"),
            ("debit", "Debit", 120, "e"),
            ("credit", "Credit", 120, "e"),
            ("running", "Running Balance", 140, "e"),
        ):
            self.gl_tree.heading(col, text=heading)
            self.gl_tree.column(col, width=width, anchor=anchor)
        self.gl_tree.pack(fill="both", expand=True, padx=6, pady=6)

        self.gl_ending = tk.StringVar(value="Ending balance: " + fmt(ZERO))
        ttk.Label(tab, textvariable=self.gl_ending).pack(anchor="w", padx=6, pady=4)

    def refresh_general_ledger(self) -> None:
        self.gl_combo.configure(values=self._account_choices())

    def _gl_show(self) -> None:
        account_id = self._account_id_from_choice(self.gl_account.get())
        if account_id is None:
            messagebox.showinfo("General Ledger", "Select an account first.")
            return
        start = self.gl_start.get().strip() or None
        end = self.gl_end.get().strip() or None
        self.gl_tree.delete(*self.gl_tree.get_children())
        try:
            rows = self.ledger.ledger_lines(account_id, start=start, end=end)
        except LedgerError as exc:
            messagebox.showerror("General Ledger", str(exc))
            return
        ending = ZERO
        for row in rows:
            self.gl_tree.insert(
                "",
                "end",
                values=(
                    row.date,
                    row.memo,
                    row.reference,
                    fmt(row.debit) if row.debit != ZERO else "",
                    fmt(row.credit) if row.credit != ZERO else "",
                    fmt(row.running_balance),
                ),
            )
            ending = row.running_balance
        self.gl_ending.set("Ending balance: " + fmt(ending))

    # ------------------------------------------------------------------ #
    # Reports tab
    # ------------------------------------------------------------------ #
    def _build_reports_tab(self) -> None:
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Reports")

        controls = ttk.Frame(tab)
        controls.pack(fill="x", padx=6, pady=6)
        self.report_kind = tk.StringVar(value="trial_balance")
        for label, value in (
            ("Trial Balance", "trial_balance"),
            ("Income Statement", "income_statement"),
            ("Balance Sheet", "balance_sheet"),
        ):
            ttk.Radiobutton(
                controls, text=label, value=value, variable=self.report_kind
            ).pack(side="left", padx=6)

        ttk.Label(controls, text="As of / End:").pack(side="left", padx=4)
        self.report_as_of = tk.StringVar(value=_today())
        ttk.Entry(controls, textvariable=self.report_as_of, width=12).pack(
            side="left", padx=4
        )
        ttk.Label(controls, text="Start:").pack(side="left", padx=4)
        self.report_start = tk.StringVar()
        ttk.Entry(controls, textvariable=self.report_start, width=12).pack(
            side="left", padx=4
        )

        ttk.Button(controls, text="Generate", command=self._report_generate).pack(
            side="left", padx=8
        )
        ttk.Button(controls, text="Export CSV", command=self._report_export).pack(
            side="left", padx=4
        )

        self.report_status = tk.StringVar(value="")
        ttk.Label(tab, textvariable=self.report_status).pack(anchor="w", padx=6)

        self.report_text = tk.Text(tab, height=28, font=("Courier New", 11))
        self.report_text.pack(fill="both", expand=True, padx=6, pady=6)

        self._last_report = None

    def _report_generate(self) -> None:
        kind = self.report_kind.get()
        as_of = self.report_as_of.get().strip() or None
        start = self.report_start.get().strip() or None
        self.report_text.delete("1.0", "end")
        try:
            if kind == "trial_balance":
                report = reports.trial_balance(self.ledger, as_of=as_of)
                self._last_report = report
                self._render_trial_balance(report)
            elif kind == "income_statement":
                if not start or not as_of:
                    messagebox.showinfo(
                        "Income Statement", "Provide both Start and End dates."
                    )
                    return
                report = reports.income_statement(self.ledger, start, as_of)
                self._last_report = report
                self._render_income_statement(report)
            else:
                report = reports.balance_sheet(self.ledger, as_of=as_of)
                self._last_report = report
                self._render_balance_sheet(report)
        except LedgerError as exc:
            messagebox.showerror("Report error", str(exc))

    def _render_trial_balance(self, tb: reports.TrialBalance) -> None:
        lines = [f"TRIAL BALANCE  (as of {tb.as_of or 'latest'})", ""]
        lines.append(f"{'Account':<34}{'Debit':>14}{'Credit':>14}")
        for account, debit, credit in tb.rows:
            label = f"{account.code} {account.name}"
            lines.append(
                f"{label:<34}"
                f"{(fmt(debit) if debit != ZERO else ''):>14}"
                f"{(fmt(credit) if credit != ZERO else ''):>14}"
            )
        lines.append("")
        lines.append(
            f"{'TOTAL':<34}{fmt(tb.total_debit):>14}{fmt(tb.total_credit):>14}"
        )
        self.report_text.insert("1.0", "\n".join(lines))
        self.report_status.set(
            "Balanced" if tb.is_balanced else "NOT BALANCED"
        )

    def _render_income_statement(self, is_: reports.IncomeStatement) -> None:
        lines = [f"INCOME STATEMENT  ({is_.start} to {is_.end})", "", "Revenue:"]
        for account, amount in is_.revenue:
            lines.append(f"  {account.code} {account.name:<28}{fmt(amount):>14}")
        lines.append(f"  {'Total Revenue':<32}{fmt(is_.total_revenue):>14}")
        lines.append("")
        lines.append("Expenses:")
        for account, amount in is_.expense:
            lines.append(f"  {account.code} {account.name:<28}{fmt(amount):>14}")
        lines.append(f"  {'Total Expense':<32}{fmt(is_.total_expense):>14}")
        lines.append("")
        lines.append(f"{'NET INCOME':<34}{fmt(is_.net_income):>14}")
        self.report_text.insert("1.0", "\n".join(lines))
        self.report_status.set("")

    def _render_balance_sheet(self, bs: reports.BalanceSheet) -> None:
        lines = [f"BALANCE SHEET  (as of {bs.as_of or 'latest'})", "", "Assets:"]
        for label, amount in bs.assets:
            lines.append(f"  {label:<40}{fmt(amount):>14}")
        lines.append(f"  {'Total Assets':<40}{fmt(bs.total_assets):>14}")
        lines.append("")
        lines.append("Liabilities:")
        for label, amount in bs.liabilities:
            lines.append(f"  {label:<40}{fmt(amount):>14}")
        lines.append(f"  {'Total Liabilities':<40}{fmt(bs.total_liabilities):>14}")
        lines.append("")
        lines.append("Equity:")
        for label, amount in bs.equity:
            lines.append(f"  {label:<40}{fmt(amount):>14}")
        lines.append(f"  {'Total Equity':<40}{fmt(bs.total_equity):>14}")
        self.report_text.insert("1.0", "\n".join(lines))
        self.report_status.set("Balanced" if bs.is_balanced else "NOT BALANCED")

    def _report_export(self) -> None:
        if self._last_report is None:
            messagebox.showinfo("Export", "Generate a report first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")]
        )
        if not path:
            return
        try:
            if isinstance(self._last_report, reports.TrialBalance):
                reports.export_trial_balance_csv(self._last_report, path)
            elif isinstance(self._last_report, reports.IncomeStatement):
                reports.export_income_statement_csv(self._last_report, path)
            elif isinstance(self._last_report, reports.BalanceSheet):
                reports.export_balance_sheet_csv(self._last_report, path)
            messagebox.showinfo("Export", f"Saved to {path}")
        except Exception as exc:  # pragma: no cover - GUI guard
            messagebox.showerror("Export failed", str(exc))

    # ------------------------------------------------------------------ #
    # Global refresh
    # ------------------------------------------------------------------ #
    def refresh_all(self) -> None:
        """Refresh every tab from the current ledger state."""
        self.refresh_accounts()
        self.refresh_journal()
        self.refresh_general_ledger()
