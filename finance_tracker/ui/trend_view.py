from io import BytesIO
from collections import defaultdict
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QTableWidget, QTableWidgetItem, QAbstractItemView
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

from sqlalchemy import func, extract, case

from finance_tracker.data.db import SessionLocal
from finance_tracker.data.models import Transaction, Account


def effective_date_expr():
    return func.coalesce(Transaction.post_date, Transaction.transaction_date)


def fig_to_pixmap(fig):
    buf = BytesIO()
    fig.tight_layout()
    FigureCanvasAgg(fig).print_png(buf)
    pixmap = QPixmap()
    pixmap.loadFromData(buf.getvalue(), 'PNG')
    plt.close(fig)
    return pixmap


def normalize_merchant(text):
    text = (text or '').upper()
    text = re.sub(r'\d+', '', text)
    text = re.sub(r'[^A-Z ]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:40]


class TrendView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = SessionLocal()
        self.setup_ui()
        self.refresh_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        title = QLabel('Ongoing Trend View')
        title.setStyleSheet('font-size: 18px; font-weight: bold;')
        layout.addWidget(title)

        self.summary_label = QLabel('')
        self.summary_label.setStyleSheet('font-size: 13px; color: #aaaaaa;')
        layout.addWidget(self.summary_label)

        row = QHBoxLayout()
        self.cashflow_chart = QLabel('')
        self.networth_chart = QLabel('')
        self.cashflow_chart.setAlignment(Qt.AlignCenter)
        self.networth_chart.setAlignment(Qt.AlignCenter)
        row.addWidget(self.cashflow_chart)
        row.addWidget(self.networth_chart)
        layout.addLayout(row)

        self.recurring_table = QTableWidget()
        self.recurring_table.setColumnCount(6)
        self.recurring_table.setHorizontalHeaderLabels(['Recurring Candidate', 'Occurrences', 'Avg Amount', 'First Seen', 'Last Seen', 'Span Months'])
        self.recurring_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.recurring_table.verticalHeader().setVisible(False)
        layout.addWidget(self.recurring_table)

    def refresh_data(self):
        eff = effective_date_expr()
        rows = (
            self.session.query(
                extract('year', eff).label('yr'),
                extract('month', eff).label('mo'),
                func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0.0)).label('income'),
                func.sum(case((Transaction.amount < 0, -Transaction.amount), else_=0.0)).label('expense'),
                func.sum(Transaction.amount).label('net'),
            )
            .group_by('yr', 'mo')
            .order_by(extract('year', eff), extract('month', eff))
            .all()
        )

        labels = [f"{int(r.yr):04d}-{int(r.mo):02d}" for r in rows]
        incomes = [float(r.income or 0) for r in rows]
        expenses = [float(r.expense or 0) for r in rows]
        nets = [float(r.net or 0) for r in rows]

        self.summary_label.setText(f'Months tracked: {len(labels)}  |  Total net cash flow: ${sum(nets):,.2f}')
        self._render_cashflow(labels, incomes, expenses, nets)
        self._render_networth(labels)
        self._load_recurring()

    def _render_cashflow(self, labels, incomes, expenses, nets):
        fig, ax = plt.subplots(figsize=(8, 4), dpi=120)
        if labels:
            ax.plot(labels, incomes, marker='o', label='Income', color='#4caf50')
            ax.plot(labels, expenses, marker='o', label='Expenses', color='#f44336')
            ax.bar(labels, nets, alpha=0.35, label='Net Cash Flow', color='#2196f3')
            ax.legend()
            ax.set_title('Monthly Cash Flow Trend')
            ax.tick_params(axis='x', rotation=45)
        else:
            ax.text(0.5, 0.5, 'No transaction data', ha='center', va='center')
            ax.axis('off')
        self.cashflow_chart.setPixmap(fig_to_pixmap(fig).scaled(760, 380, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _render_networth(self, labels):
        fig, ax = plt.subplots(figsize=(8, 4), dpi=120)
        if not labels:
            ax.text(0.5, 0.5, 'No account or transaction data', ha='center', va='center')
            ax.axis('off')
            self.networth_chart.setPixmap(fig_to_pixmap(fig).scaled(760, 380, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            return

        accounts = self.session.query(Account).all()
        values = []
        for label in labels:
            y, m = map(int, label.split('-'))
            total = 0.0
            for acc in accounts:
                base = float(acc.starting_balance or 0)
                total += base
                eff = effective_date_expr()
                delta = (
                    self.session.query(func.sum(Transaction.amount))
                    .filter(Transaction.account_id == acc.account_id)
                    .filter(extract('year', eff) < y)
                    .scalar()
                )
                total += float(delta or 0)
                delta2 = (
                    self.session.query(func.sum(Transaction.amount))
                    .filter(Transaction.account_id == acc.account_id)
                    .filter(extract('year', eff) == y)
                    .filter(extract('month', eff) <= m)
                    .scalar()
                )
                total += float(delta2 or 0)
            values.append(total)

        ax.plot(labels, values, marker='o', color='#7e57c2', linewidth=2)
        ax.set_title('Estimated Net Worth Trend')
        ax.tick_params(axis='x', rotation=45)
        self.networth_chart.setPixmap(fig_to_pixmap(fig).scaled(760, 380, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _load_recurring(self):
        rows = self.session.query(Transaction).all()
        groups = defaultdict(list)
        for tx in rows:
            key = normalize_merchant(tx.merchant or tx.description)
            groups[key].append(tx)

        candidates = []
        for key, items in groups.items():
            if len(items) >= 3:
                dates = sorted((t.post_date or t.transaction_date) for t in items if (t.post_date or t.transaction_date))
                if not dates:
                    continue
                amounts = [abs(float(t.amount)) for t in items]
                span_months = max(1, (dates[-1].year - dates[0].year) * 12 + (dates[-1].month - dates[0].month) + 1)
                candidates.append((key, len(items), sum(amounts)/len(amounts), dates[0], dates[-1], span_months))
        candidates.sort(key=lambda x: (-x[1], -x[5], x[0]))

        self.recurring_table.setRowCount(len(candidates))
        for i, row in enumerate(candidates):
            vals = [row[0], str(row[1]), f"${row[2]:,.2f}", row[3].isoformat(), row[4].isoformat(), str(row[5])]
            for j, val in enumerate(vals):
                self.recurring_table.setItem(i, j, QTableWidgetItem(val))
        self.recurring_table.resizeColumnsToContents()
