from collections import OrderedDict
from datetime import timedelta

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTableWidget, QTableWidgetItem, QAbstractItemView,
)
from PySide6.QtCore import Qt

from sqlalchemy import func

from finance_tracker.data.db import SessionLocal
from finance_tracker.data.models import Account, Transaction


class RunningBalanceView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = SessionLocal()
        self.setup_ui()
        self.load_accounts()
        self.refresh_data()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(12, 12, 12, 12)

        title = QLabel("Running Balance")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        main_layout.addWidget(title)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Account:"))

        self.account_combo = QComboBox()
        self.account_combo.currentIndexChanged.connect(self.refresh_data)
        filter_row.addWidget(self.account_combo)
        filter_row.addStretch()

        main_layout.addLayout(filter_row)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-size: 13px; color: #aaaaaa;")
        main_layout.addWidget(self.summary_label)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "Date", "Daily Net Change", "Running Balance", "Txn Count"
        ])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSortingEnabled(False)

        main_layout.addWidget(self.table)

    def load_accounts(self):
        current_id = self.account_combo.currentData()
        self.account_combo.blockSignals(True)
        self.account_combo.clear()

        accounts = self.session.query(Account).order_by(Account.account_name).all()
        for acc in accounts:
            self.account_combo.addItem(acc.account_name, acc.account_id)

        if current_id is not None:
            idx = self.account_combo.findData(current_id)
            if idx >= 0:
                self.account_combo.setCurrentIndex(idx)

        self.account_combo.blockSignals(False)

    def refresh_data(self):
        account_id = self.account_combo.currentData()
        self.table.setRowCount(0)

        if account_id is None:
            self.summary_label.setText("No account selected.")
            return

        account = self.session.query(Account).filter(Account.account_id == account_id).first()
        if not account:
            self.summary_label.setText("Account not found.")
            return

        if not account.starting_balance_date:
            self.summary_label.setText(
                "This account does not have a starting balance date yet."
            )
            return

        aligned_date = func.coalesce(Transaction.post_date, Transaction.transaction_date)

        rows = (
            self.session.query(
                aligned_date.label("effective_date"),
                func.sum(Transaction.amount).label("daily_amount"),
                func.count(Transaction.id).label("txn_count"),
            )
            .filter(Transaction.account_id == account_id)
            .filter(aligned_date >= account.starting_balance_date)
            .group_by(aligned_date)
            .order_by(aligned_date)
            .all()
        )

        daily_map = OrderedDict()
        for row in rows:
            daily_map[row.effective_date] = {
                "daily_amount": float(row.daily_amount or 0),
                "txn_count": int(row.txn_count or 0),
            }

        if daily_map:
            first_day = min(daily_map.keys())
            last_day = max(daily_map.keys())
        else:
            first_day = account.starting_balance_date
            last_day = account.starting_balance_date

        running_balance = float(account.starting_balance or 0)
        current_day = account.starting_balance_date
        output_rows = []

        while current_day <= last_day:
            info = daily_map.get(current_day, {"daily_amount": 0.0, "txn_count": 0})
            running_balance += info["daily_amount"]
            output_rows.append({
                "date": current_day,
                "daily_amount": info["daily_amount"],
                "running_balance": running_balance,
                "txn_count": info["txn_count"],
            })
            current_day += timedelta(days=1)

        self.table.setRowCount(len(output_rows))
        for i, row in enumerate(output_rows):
            d = QTableWidgetItem(row["date"].isoformat())
            amt = QTableWidgetItem(f"${row['daily_amount']:,.2f}")
            bal = QTableWidgetItem(f"${row['running_balance']:,.2f}")
            cnt = QTableWidgetItem(str(row["txn_count"]))

            amt.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            bal.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            cnt.setTextAlignment(Qt.AlignCenter)

            self.table.setItem(i, 0, d)
            self.table.setItem(i, 1, amt)
            self.table.setItem(i, 2, bal)
            self.table.setItem(i, 3, cnt)

        self.table.resizeColumnsToContents()

        self.summary_label.setText(
            f"Starting balance: ${float(account.starting_balance or 0):,.2f} on "
            f"{account.starting_balance_date.isoformat()}  |  "
            f"{len(output_rows)} day(s) shown"
        )