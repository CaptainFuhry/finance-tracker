# finance_tracker/ui/transactions_view.py

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QMessageBox,
    QDialog, QFormLayout, QLineEdit, QComboBox, QDialogButtonBox,
    QDateEdit, QHeaderView, QRadioButton,
)
from PySide6.QtCore import Qt, QDate, QEvent
from PySide6.QtGui import QColor

from finance_tracker.data.db import SessionLocal
from finance_tracker.data.models import Account, Transaction, Category
from finance_tracker.ui.account_filter_bar import AccountFilterBar


HIGHLIGHT_COLOR = QColor("#1e3a5f")
NORMAL_COLOR    = QColor(0, 0, 0, 0)

TABLE_STYLE = """
QTableWidget {
    selection-background-color: transparent;
    selection-color: inherit;
}
QTableWidget::item:selected {
    background-color: transparent;
    color: inherit;
}
QTableWidget::item:focus {
    background-color: transparent;
    border: none;
    outline: none;
}
"""


# ── Dialogs ───────────────────────────────────────────────────────────────────

class TransactionDialog(QDialog):
    def __init__(self, parent=None, transaction=None, session=None):
        super().__init__(parent)
        self.transaction = transaction
        self.session = session or SessionLocal()
        self.setWindowTitle("Transaction")
        self.setMinimumWidth(440)

        layout = QFormLayout(self)

        self.date_input = QDateEdit()
        self.date_input.setCalendarPopup(True)
        self.date_input.setDate(QDate.currentDate())
        self.account_combo      = QComboBox()
        self.category_combo     = QComboBox()
        self.description_input  = QLineEdit()
        self.merchant_input     = QLineEdit()
        self.amount_input       = QLineEdit()
        self.amount_input.setPlaceholderText("e.g. -45.00 for debit, 1200.00 for deposit")

        self._load_accounts()
        self._load_categories()

        layout.addRow("Date:",        self.date_input)
        layout.addRow("Account:",     self.account_combo)
        layout.addRow("Category:",    self.category_combo)
        layout.addRow("Description:", self.description_input)
        layout.addRow("Merchant:",    self.merchant_input)
        layout.addRow("Amount:",      self.amount_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        if transaction:
            if transaction.transaction_date:
                d = transaction.transaction_date
                self.date_input.setDate(QDate(d.year, d.month, d.day))
            idx = self.account_combo.findData(transaction.account_id)
            if idx >= 0:
                self.account_combo.setCurrentIndex(idx)
            idx = self.category_combo.findData(transaction.category_id)
            if idx >= 0:
                self.category_combo.setCurrentIndex(idx)
            self.description_input.setText(transaction.description or "")
            self.merchant_input.setText(transaction.merchant or "")
            self.amount_input.setText(str(transaction.amount))

    def _load_accounts(self):
        self.account_combo.clear()
        for a in self.session.query(Account).order_by(Account.account_name).all():
            self.account_combo.addItem(a.account_name, a.account_id)

    def _load_categories(self):
        self.category_combo.clear()
        self.category_combo.addItem("(none)", None)
        for c in self.session.query(Category).order_by(Category.name).all():
            self.category_combo.addItem(c.name, c.id)

    def get_data(self):
        return {
            "transaction_date": self.date_input.date().toPython(),
            "account_id":       self.account_combo.currentData(),
            "category_id":      self.category_combo.currentData(),
            "description":      self.description_input.text().strip(),
            "merchant":         self.merchant_input.text().strip(),
            "amount":           self.amount_input.text().strip(),
        }


class BulkCategoryDialog(QDialog):
    def __init__(self, parent=None, session=None, count=0):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle("Bulk Assign Category")
        self.setMinimumWidth(360)
        layout = QFormLayout(self)
        layout.addRow(QLabel(f"Assign category to <b>{count}</b> selected transaction(s):"))
        self.category_combo = QComboBox()
        self.category_combo.addItem("(none — clear category)", None)
        for c in self.session.query(Category).order_by(Category.name).all():
            self.category_combo.addItem(c.name, c.id)
        layout.addRow("Category:", self.category_combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_category_id(self):
        return self.category_combo.currentData()


# ── Main view ─────────────────────────────────────────────────────────────────

class TransactionsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.session             = SessionLocal()
        self._current_account_id = None
        self._radio_buttons      = {}
        self._row_to_tx_id       = {}
        self._selected_rows      = set()
        self._selected_tx_ids    = set()
        self._anchor_row         = -1
        self.setup_ui()
        self.load_transactions()

    # ── UI ────────────────────────────────────────────────────────────────────

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(12, 12, 12, 12)

        title = QLabel("Transactions")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        main_layout.addWidget(title)

        self.filter_bar = AccountFilterBar()
        self.filter_bar.account_changed.connect(self._on_account_filter_changed)
        main_layout.addWidget(self.filter_bar)

        btn_row = QHBoxLayout()
        self.add_button      = QPushButton("Add Transaction")
        self.edit_button     = QPushButton("Edit Transaction")
        self.delete_button   = QPushButton("Delete Transaction")
        self.bulk_cat_button = QPushButton("Assign Category to Selected")
        self.bulk_cat_button.setEnabled(False)
        btn_row.addWidget(self.add_button)
        btn_row.addWidget(self.edit_button)
        btn_row.addWidget(self.delete_button)
        btn_row.addSpacing(16)
        btn_row.addWidget(self.bulk_cat_button)
        btn_row.addStretch()
        main_layout.addLayout(btn_row)

        self.totals_label = QLabel("")
        self.totals_label.setStyleSheet("font-size: 13px; color: #aaaaaa;")
        main_layout.addWidget(self.totals_label)

        self.table = QTableWidget()
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "", "ID", "Date", "Post Date", "Account",
            "Category", "Description", "Merchant", "Amount",
        ])
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 36)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setSortingEnabled(True)
        self.table.setFocusPolicy(Qt.StrongFocus)

        # viewport filter → intercepts mouse (ctrl/shift clicks)
        self.table.viewport().installEventFilter(self)
        # table filter → intercepts keyboard (Enter key)
        self.table.installEventFilter(self)

        main_layout.addWidget(self.table)

        self.add_button.clicked.connect(self.add_transaction)
        self.edit_button.clicked.connect(self.edit_transaction)
        self.delete_button.clicked.connect(self.delete_transaction)
        self.bulk_cat_button.clicked.connect(self.bulk_assign_category)

    # ── Event filter ──────────────────────────────────────────────────────────

    def eventFilter(self, source, event):
        # ── Mouse clicks on viewport (ctrl/shift multi-select) ────────────────
        if source is self.table.viewport() and event.type() == QEvent.Type.MouseButtonPress:
            index = self.table.indexAt(event.pos())
            if index.isValid():
                row  = index.row()
                mods = event.modifiers()

                print(f"[TX] click row={row}  ctrl={bool(mods & Qt.ControlModifier)}  "
                      f"shift={bool(mods & Qt.ShiftModifier)}  "
                      f"before={sorted(self._selected_rows)}")

                if (mods & Qt.ShiftModifier) and self._anchor_row >= 0:
                    lo, hi = min(self._anchor_row, row), max(self._anchor_row, row)
                    self._selected_rows = set(range(lo, hi + 1))
                elif mods & Qt.ControlModifier:
                    if row in self._selected_rows:
                        self._selected_rows.discard(row)
                    else:
                        self._selected_rows.add(row)
                    self._anchor_row = row
                else:
                    self._selected_rows = {row}
                    self._anchor_row    = row

                print(f"[TX]       after={sorted(self._selected_rows)}")
                self._sync_from_rows()
            return True   # block Qt's own mouse handling

        # ── Key presses on the table (Enter → edit) ───────────────────────────
        if source is self.table and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.edit_transaction()
                return True   # consumed

        return super().eventFilter(source, event)

    # ── Selection sync ────────────────────────────────────────────────────────

    def _sync_from_rows(self):
        self._selected_tx_ids = set()
        for row in self._selected_rows:
            tx_id = self._row_to_tx_id.get(row)
            if tx_id is not None:
                self._selected_tx_ids.add(tx_id)

        anchor_tx_id = self._row_to_tx_id.get(self._anchor_row)
        for tx_id, radio in self._radio_buttons.items():
            radio.blockSignals(True)
            radio.setChecked(tx_id == anchor_tx_id)
            radio.blockSignals(False)

        for row in range(self.table.rowCount()):
            bg = HIGHLIGHT_COLOR if row in self._selected_rows else NORMAL_COLOR
            for col in range(1, self.table.columnCount()):
                item = self.table.item(row, col)
                if item:
                    item.setBackground(bg)

        self.bulk_cat_button.setEnabled(len(self._selected_tx_ids) > 0)
        self._update_totals_label()

    # ── Filter bar ────────────────────────────────────────────────────────────

    def _on_account_filter_changed(self, account_id):
        self._current_account_id = account_id
        self._clear_selection()
        self.load_transactions()

    def _clear_selection(self):
        self._selected_rows.clear()
        self._selected_tx_ids.clear()
        self._anchor_row = -1

    # ── Load ─────────────────────────────────────────────────────────────────

    def load_transactions(self, account_id=None):
        filter_id = account_id if account_id is not None else self._current_account_id

        query = (
            self.session.query(Transaction)
            .order_by(Transaction.transaction_date.desc())
        )
        if filter_id is not None:
            query = query.filter(Transaction.account_id == filter_id)

        rows = query.all()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._radio_buttons = {}
        self._row_to_tx_id  = {}
        self._clear_selection()
        total_amount = 0.0

        for row_index, tx in enumerate(rows):
            self.table.insertRow(row_index)
            self._row_to_tx_id[row_index] = tx.id
            amount = float(tx.amount) if tx.amount is not None else 0.0
            total_amount += amount

            radio = QRadioButton()
            radio.setProperty("tx_id", tx.id)
            radio.setStyleSheet("margin-left: 8px;")
            radio.clicked.connect(self._on_radio_clicked)
            self._radio_buttons[tx.id] = radio
            self.table.setCellWidget(row_index, 0, radio)

            self.table.setItem(row_index, 1, QTableWidgetItem(str(tx.id)))
            date_str = tx.transaction_date.strftime("%Y-%m-%d") if tx.transaction_date else ""
            self.table.setItem(row_index, 2, QTableWidgetItem(date_str))
            post_str = tx.post_date.strftime("%Y-%m-%d") if getattr(tx, "post_date", None) else ""
            self.table.setItem(row_index, 3, QTableWidgetItem(post_str))
            self.table.setItem(row_index, 4, QTableWidgetItem(
                tx.account.account_name if tx.account else ""))
            self.table.setItem(row_index, 5, QTableWidgetItem(
                tx.category.name if tx.category else ""))
            self.table.setItem(row_index, 6, QTableWidgetItem(tx.description or ""))
            self.table.setItem(row_index, 7, QTableWidgetItem(tx.merchant or ""))

            amount_item = QTableWidgetItem(f"${amount:,.2f}")
            amount_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            amount_item.setForeground(
                QColor("#f44336") if amount < 0 else QColor("#4caf50"))
            self.table.setItem(row_index, 8, amount_item)

        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, 36)
        self.table.setSortingEnabled(True)
        self.bulk_cat_button.setEnabled(False)
        self._update_totals_label(total_amount=total_amount, count=len(rows))

    def _on_radio_clicked(self):
        tx_id = self.sender().property("tx_id")
        target_row = next(
            (r for r, tid in self._row_to_tx_id.items() if tid == tx_id), None)
        if target_row is None:
            return
        self._selected_rows = {target_row}
        self._anchor_row    = target_row
        self._sync_from_rows()

    def _update_totals_label(self, total_amount=None, count=None):
        if count is None:
            count = self.table.rowCount()
        if total_amount is None:
            total_amount = 0.0
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 8)
                if item:
                    try:
                        total_amount += float(
                            item.text().replace("$", "").replace(",", ""))
                    except ValueError:
                        pass
        sel_count = len(self._selected_tx_ids)
        color     = "#4caf50" if total_amount >= 0 else "#f44336"
        sel_text  = f"  |  <b>{sel_count}</b> selected" if sel_count > 0 else ""
        self.totals_label.setText(
            f"Showing <b>{count}</b> transaction{'s' if count != 1 else ''}"
            f"  |  Net: <span style='color:{color};'><b>${total_amount:,.2f}</b></span>"
            f"{sel_text}"
        )

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def get_single_selected_transaction(self):
        if len(self._selected_tx_ids) != 1:
            return None
        tx_id = next(iter(self._selected_tx_ids))
        return self.session.query(Transaction).filter(Transaction.id == tx_id).first()

    def add_transaction(self):
        dialog = TransactionDialog(self, session=self.session)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            if not data["account_id"]:
                QMessageBox.warning(self, "Validation Error", "Please select an account.")
                return
            try:
                amount = float(data["amount"])
            except ValueError:
                QMessageBox.warning(self, "Validation Error",
                    "Amount must be a valid number.")
                return
            self.session.add(Transaction(
                transaction_date=data["transaction_date"],
                account_id=data["account_id"],
                category_id=data["category_id"],
                description=data["description"],
                merchant=data["merchant"],
                amount=amount,
            ))
            self.session.commit()
            self.load_transactions()

    def edit_transaction(self):
        tx = self.get_single_selected_transaction()
        if not tx:
            msg = (
                "Only one transaction can be edited at a time.\n"
                "Use 'Assign Category to Selected' for bulk changes."
                if len(self._selected_tx_ids) > 1
                else "Please select a transaction to edit."
            )
            QMessageBox.information(self, "Select Transaction", msg)
            return
        dialog = TransactionDialog(self, transaction=tx, session=self.session)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            if not data["account_id"]:
                QMessageBox.warning(self, "Validation Error", "Please select an account.")
                return
            try:
                amount = float(data["amount"])
            except ValueError:
                QMessageBox.warning(self, "Validation Error",
                    "Amount must be a valid number.")
                return
            tx.transaction_date = data["transaction_date"]
            tx.account_id       = data["account_id"]
            tx.category_id      = data["category_id"]
            tx.description      = data["description"]
            tx.merchant         = data["merchant"]
            tx.amount           = amount
            self.session.commit()
            self.load_transactions()

    def delete_transaction(self):
        tx = self.get_single_selected_transaction()
        if not tx:
            QMessageBox.information(self, "Select Transaction",
                "Please select a single transaction to delete.")
            return
        if QMessageBox.question(
            self, "Confirm Delete",
            f"Delete transaction: {tx.description or tx.id}?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        ) == QMessageBox.Yes:
            self.session.delete(tx)
            self.session.commit()
            self.load_transactions()

    def bulk_assign_category(self):
        if not self._selected_tx_ids:
            QMessageBox.information(self, "Nothing Selected",
                "Select one or more transactions first.")
            return
        dialog = BulkCategoryDialog(
            self, session=self.session, count=len(self._selected_tx_ids))
        if dialog.exec() == QDialog.Accepted:
            category_id = dialog.get_category_id()
            for tx in self.session.query(Transaction).filter(
                Transaction.id.in_(self._selected_tx_ids)
            ).all():
                tx.category_id = category_id
            self.session.commit()
            self.load_transactions()
