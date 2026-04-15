# finance_tracker/ui/accounts_view.py

from decimal import Decimal
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QAbstractItemView,
    QMessageBox,
    QDialog,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QDialogButtonBox,
    QHeaderView,
    QRadioButton,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from finance_tracker.data.db import SessionLocal
from finance_tracker.data.models import Account, Transaction
from sqlalchemy import func


class AccountDialog(QDialog):
    def __init__(self, parent=None, account=None):
        super().__init__(parent)
        self.account = account
        self.setWindowTitle("Account")
        self.setMinimumWidth(400)

        layout = QFormLayout(self)

        self.name_input = QLineEdit()
        self.institution_input = QLineEdit()
        self.type_input = QComboBox()
        self.type_input.addItems(["Checking", "Savings", "Credit Card", "Loan", "Other"])
        self.balance_input = QLineEdit()
        self.balance_input.setPlaceholderText("0.00")

        layout.addRow("Account Name:", self.name_input)
        layout.addRow("Institution:", self.institution_input)
        layout.addRow("Account Type:", self.type_input)
        layout.addRow("Starting Balance:", self.balance_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        if account:
            self.name_input.setText(account.account_name or "")
            self.institution_input.setText(account.institution or "")
            self.type_input.setCurrentText(account.account_type or "Checking")
            self.balance_input.setText(str(account.starting_balance))

    def get_data(self):
        return {
            "account_name": self.name_input.text().strip(),
            "institution": self.institution_input.text().strip(),
            "account_type": self.type_input.currentText(),
            "starting_balance": self.balance_input.text().strip(),
        }


class AccountsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = SessionLocal()
        self._selected_account_id = None
        self._radio_buttons = {}
        self.setup_ui()
        self.load_accounts()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(12, 12, 12, 12)

        title = QLabel("Accounts")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        main_layout.addWidget(title)

        button_layout = QHBoxLayout()
        self.add_button = QPushButton("Add Account")
        self.edit_button = QPushButton("Edit Account")
        self.deactivate_button = QPushButton("Deactivate Account")
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.edit_button)
        button_layout.addWidget(self.deactivate_button)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "", "ID", "Account Name", "Institution",
            "Account Type", "Starting Balance", "Current Balance",
        ])
        # No selection at all — radio button is the only selector
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 36)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setFocusPolicy(Qt.NoFocus)
        main_layout.addWidget(self.table)

        self.add_button.clicked.connect(self.add_account)
        self.edit_button.clicked.connect(self.edit_account)
        self.deactivate_button.clicked.connect(self.deactivate_account)

    def load_accounts(self):
        accounts = self.session.query(Account).order_by(Account.account_name).all()

        tx_totals = dict(
            self.session.query(
                Transaction.account_id,
                func.sum(Transaction.amount)
            ).group_by(Transaction.account_id).all()
        )

        self.table.setRowCount(0)
        self._radio_buttons = {}

        for row_index, account in enumerate(accounts):
            tx_sum = tx_totals.get(account.account_id, 0) or 0
            current_balance = float(account.starting_balance) + float(tx_sum)

            self.table.insertRow(row_index)

            radio = QRadioButton()
            radio.setProperty("account_id", account.account_id)
            radio.setStyleSheet("margin-left: 8px;")
            radio.toggled.connect(self._on_radio_toggled)
            self._radio_buttons[account.account_id] = radio
            self.table.setCellWidget(row_index, 0, radio)

            self.table.setItem(row_index, 1, QTableWidgetItem(str(account.account_id)))
            self.table.setItem(row_index, 2, QTableWidgetItem(account.account_name or ""))
            self.table.setItem(row_index, 3, QTableWidgetItem(account.institution or ""))
            self.table.setItem(row_index, 4, QTableWidgetItem(account.account_type or ""))

            start_item = QTableWidgetItem(f"${float(account.starting_balance):,.2f}")
            start_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row_index, 5, start_item)

            balance_item = QTableWidgetItem(f"${current_balance:,.2f}")
            balance_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            balance_item.setForeground(
                QColor("#4caf50") if current_balance >= 0 else QColor("#f44336")
            )
            self.table.setItem(row_index, 6, balance_item)

        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, 36)

        if self._selected_account_id and self._selected_account_id in self._radio_buttons:
            self._radio_buttons[self._selected_account_id].setChecked(True)

    def _on_radio_toggled(self, checked):
        if checked:
            self._selected_account_id = self.sender().property("account_id")

    def get_selected_account_id(self):
        return self._selected_account_id

    def add_account(self):
        dialog = AccountDialog(self)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            if not data["account_name"]:
                QMessageBox.warning(self, "Validation Error", "Account name is required.")
                return
            try:
                starting_balance = Decimal(data["starting_balance"] or "0")
            except Exception:
                QMessageBox.warning(self, "Validation Error", "Starting balance must be a valid number.")
                return
            account = Account(
                account_name=data["account_name"],
                institution=data["institution"],
                account_type=data["account_type"],
                starting_balance=starting_balance,
                created_at=datetime.now(),
            )
            self.session.add(account)
            self.session.commit()
            self.load_accounts()

    def edit_account(self):
        if not self._selected_account_id:
            QMessageBox.information(self, "Select Account",
                "Please select an account using the radio button.")
            return
        account = self.session.query(Account).filter(
            Account.account_id == self._selected_account_id
        ).first()
        if not account:
            QMessageBox.warning(self, "Not Found", "Selected account could not be found.")
            return
        dialog = AccountDialog(self, account)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            if not data["account_name"]:
                QMessageBox.warning(self, "Validation Error", "Account name is required.")
                return
            try:
                starting_balance = Decimal(data["starting_balance"] or "0")
            except Exception:
                QMessageBox.warning(self, "Validation Error", "Starting balance must be a valid number.")
                return
            account.account_name = data["account_name"]
            account.institution = data["institution"]
            account.account_type = data["account_type"]
            account.starting_balance = starting_balance
            self.session.commit()
            self.load_accounts()

    def deactivate_account(self):
        if not self._selected_account_id:
            QMessageBox.information(self, "Select Account",
                "Please select an account using the radio button.")
            return
        account = self.session.query(Account).filter(
            Account.account_id == self._selected_account_id
        ).first()
        if not account:
            QMessageBox.warning(self, "Not Found", "Selected account could not be found.")
            return
        QMessageBox.information(self, "Not Implemented",
            f"Deactivate is not yet available for '{account.account_name}'.")