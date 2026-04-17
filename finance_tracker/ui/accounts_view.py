from decimal import Decimal
from datetime import date, datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QMessageBox,
    QDialog, QFormLayout, QLineEdit, QComboBox, QDialogButtonBox,
    QHeaderView, QRadioButton, QCheckBox, QDateEdit,
)
from PySide6.QtCore import Qt, QEvent, QDate
from PySide6.QtGui import QColor

from finance_tracker.data.db import SessionLocal
from finance_tracker.data.models import Account


HIGHLIGHT_COLOR = QColor("#1e3a5f")
NORMAL_COLOR = QColor(0, 0, 0, 0)

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


class AccountDialog(QDialog):
    def __init__(self, parent=None, account=None, session=None):
        super().__init__(parent)
        self.session = session or SessionLocal()
        self.setWindowTitle("Account")
        self.setMinimumWidth(420)

        layout = QFormLayout(self)

        self.account_name_input = QLineEdit()
        self.account_name_input.setPlaceholderText("e.g. Chase Sapphire")

        self.institution_input = QLineEdit()
        self.institution_input.setPlaceholderText("e.g. Chase")

        self.account_type_combo = QComboBox()
        self.account_type_combo.addItems([
            "checking", "savings", "credit", "investment", "loan", "cash", "other"
        ])

        self.starting_balance_input = QLineEdit()
        self.starting_balance_input.setPlaceholderText("0.00")

        self.starting_balance_date_edit = QDateEdit()
        self.starting_balance_date_edit.setCalendarPopup(True)
        self.starting_balance_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.starting_balance_date_edit.setDate(QDate.currentDate())

        self.active_check = QCheckBox("Account is active")
        self.active_check.setChecked(True)

        layout.addRow("Account Name:", self.account_name_input)
        layout.addRow("Institution:", self.institution_input)
        layout.addRow("Account Type:", self.account_type_combo)
        layout.addRow("Starting Balance:", self.starting_balance_input)
        layout.addRow("Starting Balance Date:", self.starting_balance_date_edit)
        layout.addRow("", self.active_check)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        if account:
            self.account_name_input.setText(account.account_name or "")
            self.institution_input.setText(account.institution or "")
            idx = self.account_type_combo.findText(account.account_type or "", Qt.MatchFixedString)
            if idx >= 0:
                self.account_type_combo.setCurrentIndex(idx)
            self.starting_balance_input.setText(str(account.starting_balance or "0.00"))
            if account.starting_balance_date:
                self.starting_balance_date_edit.setDate(
                    QDate(
                        account.starting_balance_date.year,
                        account.starting_balance_date.month,
                        account.starting_balance_date.day,
                    )
                )

    def get_data(self):
        try:
            starting_balance = Decimal(self.starting_balance_input.text().strip() or "0")
        except Exception:
            starting_balance = None

        qd = self.starting_balance_date_edit.date()
        starting_balance_date = date(qd.year(), qd.month(), qd.day())

        return {
            "account_name": self.account_name_input.text().strip(),
            "institution": self.institution_input.text().strip(),
            "account_type": self.account_type_combo.currentText().strip(),
            "starting_balance": starting_balance,
            "starting_balance_date": starting_balance_date,
            "is_active": self.active_check.isChecked(),
        }


class AccountsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = SessionLocal()
        self._selected_account_id = None
        self._radio_buttons = {}
        self._row_to_account_id = {}
        self._selected_rows = set()
        self._anchor_row = -1
        self.setup_ui()
        self.load_accounts()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(12, 12, 12, 12)

        title = QLabel("Accounts")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        main_layout.addWidget(title)

        btn_row = QHBoxLayout()
        self.add_button = QPushButton("Add Account")
        self.edit_button = QPushButton("Edit Account")
        self.deactivate_button = QPushButton("Deactivate Account")
        btn_row.addWidget(self.add_button)
        btn_row.addWidget(self.edit_button)
        btn_row.addWidget(self.deactivate_button)
        btn_row.addStretch()
        main_layout.addLayout(btn_row)

        self.table = QTableWidget()
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "", "ID", "Account Name", "Institution", "Type",
            "Starting Balance", "Starting Balance Date",
        ])
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 36)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setSortingEnabled(True)
        self.table.setFocusPolicy(Qt.StrongFocus)
        self.table.viewport().installEventFilter(self)

        main_layout.addWidget(self.table)

        self.add_button.clicked.connect(self.add_account)
        self.edit_button.clicked.connect(self.edit_account)
        self.deactivate_button.clicked.connect(self.deactivate_account)

    def eventFilter(self, source, event):
        if source is self.table.viewport() and event.type() == QEvent.Type.MouseButtonPress:
            index = self.table.indexAt(event.pos())
            if index.isValid():
                row = index.row()
                mods = event.modifiers()

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
                    self._anchor_row = row

                self._sync_from_rows()
            return True
        return super().eventFilter(source, event)

    def _sync_from_rows(self):
        anchor_account_id = self._row_to_account_id.get(self._anchor_row)
        self._selected_account_id = anchor_account_id

        for account_id, radio in self._radio_buttons.items():
            radio.blockSignals(True)
            radio.setChecked(account_id == anchor_account_id)
            radio.blockSignals(False)

        for row in range(self.table.rowCount()):
            bg = HIGHLIGHT_COLOR if row in self._selected_rows else NORMAL_COLOR
            for col in range(1, self.table.columnCount()):
                item = self.table.item(row, col)
                if item:
                    item.setBackground(bg)

    def load_accounts(self):
        accounts = self.session.query(Account).order_by(Account.account_name).all()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._radio_buttons = {}
        self._row_to_account_id = {}
        self._selected_rows.clear()
        self._anchor_row = -1

        for row_index, acc in enumerate(accounts):
            self.table.insertRow(row_index)
            self._row_to_account_id[row_index] = acc.account_id

            radio = QRadioButton()
            radio.setProperty("account_id", acc.account_id)
            radio.setStyleSheet("margin-left: 8px;")
            radio.clicked.connect(self._on_radio_clicked)
            self._radio_buttons[acc.account_id] = radio
            self.table.setCellWidget(row_index, 0, radio)

            self.table.setItem(row_index, 1, QTableWidgetItem(str(acc.account_id)))
            self.table.setItem(row_index, 2, QTableWidgetItem(acc.account_name or ""))
            self.table.setItem(row_index, 3, QTableWidgetItem(acc.institution or ""))
            self.table.setItem(row_index, 4, QTableWidgetItem(acc.account_type or ""))
            self.table.setItem(row_index, 5, QTableWidgetItem(f"${float(acc.starting_balance or 0):,.2f}"))
            self.table.setItem(
                row_index,
                6,
                QTableWidgetItem(
                    acc.starting_balance_date.isoformat() if acc.starting_balance_date else ""
                ),
            )

        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, 36)
        self.table.setSortingEnabled(True)

    def _on_radio_clicked(self):
        account_id = self.sender().property("account_id")
        target_row = next(
            (r for r, aid in self._row_to_account_id.items() if aid == account_id), None
        )
        if target_row is None:
            return
        self._selected_rows = {target_row}
        self._anchor_row = target_row
        self._sync_from_rows()

    def get_selected_account(self):
        if not self._selected_account_id:
            return None
        return self.session.query(Account).filter(
            Account.account_id == self._selected_account_id
        ).first()

    def add_account(self):
        dialog = AccountDialog(self, session=self.session)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            if not data["account_name"]:
                QMessageBox.warning(self, "Validation Error", "Account name is required.")
                return
            if not data["institution"]:
                QMessageBox.warning(self, "Validation Error", "Institution is required.")
                return
            if data["starting_balance"] is None:
                QMessageBox.warning(self, "Validation Error", "Starting balance must be numeric.")
                return

            self.session.add(Account(
                account_name=data["account_name"],
                institution=data["institution"],
                account_type=data["account_type"],
                starting_balance=data["starting_balance"],
                starting_balance_date=data["starting_balance_date"],
            ))
            self.session.commit()
            self.load_accounts()

    def edit_account(self):
        acc = self.get_selected_account()
        if not acc:
            QMessageBox.information(self, "Select Account", "Please select an account.")
            return

        dialog = AccountDialog(self, account=acc, session=self.session)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            if not data["account_name"]:
                QMessageBox.warning(self, "Validation Error", "Account name is required.")
                return
            if not data["institution"]:
                QMessageBox.warning(self, "Validation Error", "Institution is required.")
                return
            if data["starting_balance"] is None:
                QMessageBox.warning(self, "Validation Error", "Starting balance must be numeric.")
                return

            acc.account_name = data["account_name"]
            acc.institution = data["institution"]
            acc.account_type = data["account_type"]
            acc.starting_balance = data["starting_balance"]
            acc.starting_balance_date = data["starting_balance_date"]
            self.session.commit()
            self.load_accounts()

    def deactivate_account(self):
        acc = self.get_selected_account()
        if not acc:
            QMessageBox.information(self, "Select Account", "Please select an account.")
            return

        if QMessageBox.question(
            self,
            "Confirm Deactivate",
            f"Deactivate account '{acc.account_name}'?",
            QMessageBox.Yes | QMessageBox.No,
        ) == QMessageBox.Yes:
            acc.account_name = f"{acc.account_name} [inactive]"
            self.session.commit()
            self.load_accounts()