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
)

from finance_tracker.data.db import SessionLocal
from finance_tracker.data.models import Account


class AccountDialog(QDialog):
    def __init__(self, parent=None, account=None):
        super().__init__(parent)
        self.account = account
        self.setWindowTitle("Account")

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
        self.setup_ui()
        self.load_accounts()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)

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
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Account ID",
            "Account Name",
            "Institution",
            "Account Type",
            "Starting Balance",
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        main_layout.addWidget(self.table)

        self.add_button.clicked.connect(self.add_account)
        self.edit_button.clicked.connect(self.edit_account)
        self.deactivate_button.clicked.connect(self.deactivate_account)

    def load_accounts(self):
        accounts = self.session.query(Account).order_by(Account.account_name).all()
        self.table.setRowCount(0)

        for row_index, account in enumerate(accounts):
            self.table.insertRow(row_index)
            self.table.setItem(row_index, 0, QTableWidgetItem(str(account.account_id)))
            self.table.setItem(row_index, 1, QTableWidgetItem(account.account_name))
            self.table.setItem(row_index, 2, QTableWidgetItem(account.institution))
            self.table.setItem(row_index, 3, QTableWidgetItem(account.account_type))
            self.table.setItem(row_index, 4, QTableWidgetItem(str(account.starting_balance)))

        self.table.resizeColumnsToContents()

    def get_selected_account_id(self):
        selected_row = self.table.currentRow()
        if selected_row < 0:
            return None

        item = self.table.item(selected_row, 0)
        if not item:
            return None

        return int(item.text())

    def add_account(self):
        dialog = AccountDialog(self)

        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()

            if not data["account_name"]:
                QMessageBox.warning(self, "Validation Error", "Account name is required.")
                return

            if not data["institution"]:
                QMessageBox.warning(self, "Validation Error", "Institution is required.")
                return

            try:
                starting_balance = Decimal(data["starting_balance"])
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
        account_id = self.get_selected_account_id()

        if not account_id:
            QMessageBox.information(self, "Select Account", "Please select an account to edit.")
            return

        account = self.session.query(Account).filter(Account.account_id == account_id).first()
        if not account:
            QMessageBox.warning(self, "Not Found", "Selected account could not be found.")
            return

        dialog = AccountDialog(self, account)

        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()

            if not data["account_name"]:
                QMessageBox.warning(self, "Validation Error", "Account name is required.")
                return

            if not data["institution"]:
                QMessageBox.warning(self, "Validation Error", "Institution is required.")
                return

            try:
                starting_balance = Decimal(data["starting_balance"])
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
        account_id = self.get_selected_account_id()

        if not account_id:
            QMessageBox.information(self, "Select Account", "Please select an account to deactivate.")
            return

        account = self.session.query(Account).filter(Account.account_id == account_id).first()
        if not account:
            QMessageBox.warning(self, "Not Found", "Selected account could not be found.")
            return

        QMessageBox.information(
            self,
            "Not Implemented",
            f"Deactivate Account is not available yet because the accounts table does not currently include an is_active column for '{account.account_name}'."
        )