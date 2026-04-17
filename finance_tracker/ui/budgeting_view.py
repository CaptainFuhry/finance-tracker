from io import BytesIO
from datetime import date

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QMessageBox, QInputDialog,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QColor

from sqlalchemy import func, extract

from finance_tracker.data.db import SessionLocal
from finance_tracker.data.models import Category, CategoryBudget, Transaction


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


class BudgetingView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = SessionLocal()
        self.setup_ui()
        self.load_months()
        self.load_categories()
        self.refresh_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        title = QLabel('Budgeting View')
        title.setStyleSheet('font-size: 18px; font-weight: bold;')
        layout.addWidget(title)

        top = QHBoxLayout()
        top.addWidget(QLabel('Budget Month:'))
        self.month_combo = QComboBox()
        self.month_combo.currentIndexChanged.connect(self.refresh_data)
        top.addWidget(self.month_combo)
        self.add_budget_btn = QPushButton('Set / Update Budget')
        self.add_budget_btn.clicked.connect(self.set_budget)
        top.addWidget(self.add_budget_btn)
        top.addStretch()
        layout.addLayout(top)

        self.summary_label = QLabel('')
        self.summary_label.setStyleSheet('font-size: 13px; color: #aaaaaa;')
        layout.addWidget(self.summary_label)

        self.chart_label = QLabel('')
        self.chart_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.chart_label)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(['Category', 'Budget', 'Actual', 'Variance', 'Status', 'Month'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

    def load_months(self):
        cur = self.month_combo.currentData()
        self.month_combo.blockSignals(True)
        self.month_combo.clear()
        eff = effective_date_expr()
        tx_months = (
            self.session.query(extract('year', eff).label('yr'), extract('month', eff).label('mo'))
            .group_by('yr', 'mo')
            .order_by(extract('year', eff).desc(), extract('month', eff).desc())
            .all()
        )
        seen = set()
        for r in tx_months:
            d = date(int(r.yr), int(r.mo), 1)
            if d not in seen:
                self.month_combo.addItem(d.strftime('%Y-%m'), d)
                seen.add(d)
        if self.month_combo.count() == 0:
            d = date.today().replace(day=1)
            self.month_combo.addItem(d.strftime('%Y-%m'), d)
        if cur:
            idx = self.month_combo.findData(cur)
            if idx >= 0:
                self.month_combo.setCurrentIndex(idx)
        self.month_combo.blockSignals(False)

    def load_categories(self):
        self.categories = self.session.query(Category).order_by(Category.name).all()

    def refresh_data(self):
        month = self.month_combo.currentData()
        if not month:
            return
        eff = effective_date_expr()
        y, m = month.year, month.month

        actual_rows = (
            self.session.query(Category.id, Category.name, func.sum(-Transaction.amount).label('actual'))
            .join(Transaction, Transaction.category_id == Category.id)
            .filter(Transaction.amount < 0)
            .filter(extract('year', eff) == y)
            .filter(extract('month', eff) == m)
            .group_by(Category.id, Category.name)
            .all()
        )
        actual_map = {row.id: float(row.actual or 0) for row in actual_rows}

        budget_rows = (
            self.session.query(CategoryBudget)
            .filter(CategoryBudget.budget_month == month)
            .all()
        )
        budget_map = {row.category_id: float(row.budget_amount or 0) for row in budget_rows}

        display_rows = []
        for cat in self.categories:
            if cat.is_income:
                continue
            budget = budget_map.get(cat.id, 0.0)
            actual = actual_map.get(cat.id, 0.0)
            variance = budget - actual
            status = 'On Track' if variance >= 0 else 'Over Budget'
            display_rows.append((cat.name, budget, actual, variance, status, month.strftime('%Y-%m')))
        display_rows.sort(key=lambda x: x[2], reverse=True)

        self.table.setRowCount(len(display_rows))
        for i, row in enumerate(display_rows):
            for j, val in enumerate(row):
                item = QTableWidgetItem(f"${val:,.2f}" if j in [1,2,3] else str(val))
                if j == 4:
                    item.setForeground(QColor('#4caf50') if row[4] == 'On Track' else QColor('#f44336'))
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()

        total_budget = sum(r[1] for r in display_rows)
        total_actual = sum(r[2] for r in display_rows)
        total_variance = total_budget - total_actual
        self.summary_label.setText(
            f'Total Budget: ${total_budget:,.2f}  |  Actual Spend: ${total_actual:,.2f}  |  Variance: ${total_variance:,.2f}'
        )
        self._render_chart(display_rows, month)

    def _render_chart(self, rows, month):
        fig, ax = plt.subplots(figsize=(10, 4), dpi=120)
        top_rows = rows[:10]
        if top_rows:
            labels = [r[0] for r in top_rows]
            budgets = [r[1] for r in top_rows]
            actuals = [r[2] for r in top_rows]
            x = range(len(labels))
            ax.bar([i - 0.2 for i in x], budgets, width=0.4, label='Budget', color='#90caf9')
            ax.bar([i + 0.2 for i in x], actuals, width=0.4, label='Actual', color='#ef5350')
            ax.set_xticks(list(x))
            ax.set_xticklabels(labels, rotation=45, ha='right')
            ax.set_title(f'Budget vs Actual — {month.strftime("%Y-%m")}')
            ax.legend()
        else:
            ax.text(0.5, 0.5, 'No budgeting data', ha='center', va='center')
            ax.axis('off')
        self.chart_label.setPixmap(fig_to_pixmap(fig).scaled(1100, 380, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def set_budget(self):
        month = self.month_combo.currentData()
        if not month:
            return
        category_names = [c.name for c in self.categories if not c.is_income]
        if not category_names:
            QMessageBox.information(self, 'No Categories', 'Create some expense categories first.')
            return
        cat_name, ok = QInputDialog.getItem(self, 'Select Category', 'Category:', category_names, 0, False)
        if not ok or not cat_name:
            return
        amount, ok = QInputDialog.getDouble(self, 'Budget Amount', f'Enter monthly budget for {cat_name}:', 0.0, 0.0, 1_000_000.0, 2)
        if not ok:
            return
        cat = next(c for c in self.categories if c.name == cat_name)
        existing = (
            self.session.query(CategoryBudget)
            .filter(CategoryBudget.category_id == cat.id)
            .filter(CategoryBudget.budget_month == month)
            .first()
        )
        if existing:
            existing.budget_amount = amount
        else:
            self.session.add(CategoryBudget(category_id=cat.id, budget_month=month, budget_amount=amount))
        self.session.commit()
        self.refresh_data()
