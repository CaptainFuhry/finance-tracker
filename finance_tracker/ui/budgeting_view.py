from io import BytesIO
from datetime import date

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.patches import Patch

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QMessageBox, QInputDialog, QHeaderView, QCheckBox, QSplitter, QScrollArea,
)
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QPixmap, QColor

from sqlalchemy import func, extract

from finance_tracker.data.db import SessionLocal
from finance_tracker.data.models import Category, CategoryBudget, Transaction

# ── Dark theme palette ────────────────────────────────────────────────────────
DK_BG      = '#1a1a1a'
DK_SURFACE = '#242424'
DK_GRID    = '#333333'
DK_TEXT    = '#e8e8e8'
DK_DIM     = '#888888'
DK_BUDGET  = '#5c9ee8'
DK_ACTUAL  = '#ef5350'
DK_OK      = '#81c784'
DK_WARN    = '#ef5350'
DK_HOVER   = '#2e2e2e'
DK_SEL     = '#2a3a4a'

TABLE_STYLE = f"""
QTableWidget {{
    background: {DK_SURFACE};
    color: {DK_TEXT};
    gridline-color: {DK_GRID};
    selection-background-color: {DK_SEL};
    selection-color: {DK_TEXT};
    border: none;
}}
QTableWidget::item:hover {{ background: {DK_HOVER}; }}
QHeaderView::section {{
    background: {DK_BG};
    color: {DK_DIM};
    border: none;
    border-bottom: 1px solid {DK_GRID};
    padding: 4px 8px;
    font-size: 11px;
}}
QScrollBar:vertical {{ background: {DK_BG}; width: 6px; }}
QScrollBar::handle:vertical {{ background: #555555; border-radius: 3px; }}
QCheckBox {{ color: {DK_TEXT}; }}
"""


def effective_date_expr():
    return func.coalesce(Transaction.post_date, Transaction.transaction_date)


def fig_to_pixmap(fig):
    buf = BytesIO()
    fig.tight_layout(pad=1.5)
    FigureCanvasAgg(fig).print_png(buf)
    pixmap = QPixmap()
    pixmap.loadFromData(buf.getvalue(), 'PNG')
    plt.close(fig)
    return pixmap


def setup_dark_axes(ax):
    ax.set_facecolor(DK_SURFACE)
    ax.figure.patch.set_facecolor(DK_BG)
    ax.tick_params(colors=DK_DIM, labelsize=8)
    ax.xaxis.label.set_color(DK_DIM)
    ax.yaxis.label.set_color(DK_DIM)
    ax.title.set_color(DK_TEXT)
    for spine in ax.spines.values():
        spine.set_edgecolor(DK_GRID)
    ax.grid(axis='y', color=DK_GRID, linewidth=0.5, linestyle='--')
    ax.set_axisbelow(True)


class _ChartPane(QWidget):
    """Chart container that triggers a re-render whenever it is resized."""
    def __init__(self, view_ref, parent=None):
        super().__init__(parent)
        self._view = view_ref
        self.setStyleSheet(f"background: {DK_BG};")
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Avoid recursive re-renders during init before _display_rows exists
        if hasattr(self._view, '_display_rows') and self._view._display_rows:
            self._view._rerender_chart(
                self._view._hovered_row if self._view._hovered_row >= 0
                else self._view._selected_row()
            )


class BudgetingView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = SessionLocal()
        self._display_rows = []     # (name, budget, actual, variance, status, month_str)
        self._included = {}         # name -> bool (included in chart)
        self._hovered_row = -1
        self.setup_ui()
        self.load_months()
        self.load_categories()
        self.refresh_data()

    # ── UI setup ──────────────────────────────────────────────────────────────
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 8, 12, 8)

        title = QLabel('Budgeting View')
        title.setStyleSheet(f'font-size: 18px; font-weight: bold; color: {DK_TEXT};')
        layout.addWidget(title)

        top = QHBoxLayout()
        lbl = QLabel('Budget Month:')
        lbl.setStyleSheet(f'color: {DK_DIM};')
        top.addWidget(lbl)

        self.month_combo = QComboBox()
        self.month_combo.setStyleSheet(
            f'background: {DK_SURFACE}; color: {DK_TEXT}; border: 1px solid {DK_GRID};'
        )
        self.month_combo.currentIndexChanged.connect(self.refresh_data)
        top.addWidget(self.month_combo)

        self.add_budget_btn = QPushButton('Set / Update Budget')
        self.add_budget_btn.setStyleSheet(
            f'background: {DK_SURFACE}; color: {DK_TEXT}; border: 1px solid {DK_GRID};'
            'padding: 4px 12px; border-radius: 4px;'
        )
        self.add_budget_btn.clicked.connect(self.set_budget)
        top.addWidget(self.add_budget_btn)
        top.addStretch()
        layout.addLayout(top)

        self.summary_label = QLabel('')
        self.summary_label.setStyleSheet(f'font-size: 12px; color: {DK_DIM};')
        layout.addWidget(self.summary_label)

        # ── Splitter: chart (top) / table (bottom) ──────────────────────────
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setHandleWidth(6)
        self.splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background: #333333;
                border-top: 1px solid #555555;
                border-bottom: 1px solid #555555;
            }}
            QSplitter::handle:hover {{
                background: #4a4a4a;
            }}
        """)

        # Chart widget — resizes chart whenever pane height changes
        self._chart_pane = _ChartPane(self)
        self.chart_label = QLabel('')
        self.chart_label.setAlignment(Qt.AlignCenter)
        self._chart_pane.layout().addWidget(self.chart_label)
        self.splitter.addWidget(self._chart_pane)

        # Table — col 0 = checkbox, col 1-6 = data
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(['', 'Category', 'Budget', 'Actual', 'Variance', 'Status', 'Month'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.setMouseTracking(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 32)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.viewport().installEventFilter(self)

        self.splitter.addWidget(self.table)
        self.splitter.setSizes([340, 280])
        self.splitter.splitterMoved.connect(lambda pos, idx: self._rerender_chart(
            self._hovered_row if self._hovered_row >= 0 else self._selected_row()
        ))
        layout.addWidget(self.splitter, 1)

    # ── Event filter for hover ────────────────────────────────────────────────
    def eventFilter(self, source, event):
        if source is self.table.viewport():
            if event.type() == QEvent.Type.MouseMove:
                idx = self.table.indexAt(event.pos())
                row = idx.row() if idx.isValid() else -1
                if row != self._hovered_row:
                    self._hovered_row = row
                    self._rerender_chart(row if row >= 0 else self._selected_row())
            elif event.type() == QEvent.Type.Leave:
                self._hovered_row = -1
                self._rerender_chart(self._selected_row())
        return super().eventFilter(source, event)

    def _selected_row(self):
        items = self.table.selectedItems()
        return self.table.row(items[0]) if items else -1

    def _on_selection_changed(self):
        self._rerender_chart(self._selected_row())

    # ── Data loading ──────────────────────────────────────────────────────────
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
        self.session.expire_all()
        eff = effective_date_expr()
        y, m = month.year, month.month

        actual_map = {
            row.id: float(row.actual or 0)
            for row in self.session.query(
                Category.id, func.sum(-Transaction.amount).label('actual')
            )
            .join(Transaction, Transaction.category_id == Category.id)
            .filter(Transaction.amount < 0,
                    extract('year', eff) == y,
                    extract('month', eff) == m)
            .group_by(Category.id)
            .all()
        }

        budget_map = {
            row.category_id: float(row.budget_amount or 0)
            for row in self.session.query(CategoryBudget)
            .filter(CategoryBudget.budget_month == month)
            .all()
        }

        display_rows = []
        for cat in self.categories:
            if cat.is_income:
                continue
            budget = budget_map.get(cat.id, 0.0)
            actual = actual_map.get(cat.id, 0.0)
            if budget == 0.0 and actual == 0.0:
                continue
            variance = budget - actual
            status = 'On Track' if variance >= 0 else 'Over Budget'
            display_rows.append((cat.name, budget, actual, variance, status, month.strftime('%Y-%m')))

        display_rows.sort(key=lambda x: x[2], reverse=True)
        self._display_rows = display_rows

        # Preserve existing include/exclude state; new rows default to included
        for row in display_rows:
            if row[0] not in self._included:
                self._included[row[0]] = True

        # Build table
        self.table.blockSignals(True)
        self.table.setRowCount(len(display_rows))

        for i, row in enumerate(display_rows):
            name = row[0]

            # Col 0: checkbox
            chk = QCheckBox()
            chk.setChecked(self._included.get(name, True))
            chk.setStyleSheet(f'margin-left: 6px; color: {DK_TEXT};')
            chk.stateChanged.connect(lambda state, n=name: self._on_include_toggled(n, state))
            self.table.setCellWidget(i, 0, chk)

            # Cols 1-6: data
            for j, val in enumerate(row):
                text = f"${val:,.2f}" if j in (1, 2, 3) else str(val)
                item = QTableWidgetItem(text)
                if j in (1, 2, 3):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if j == 4:
                    item.setForeground(QColor(DK_OK) if row[4] == 'On Track' else QColor(DK_WARN))
                self.table.setItem(i, j + 1, item)

        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, 32)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.blockSignals(False)

        total_budget = sum(r[1] for r in display_rows)
        total_actual = sum(r[2] for r in display_rows)
        total_variance = total_budget - total_actual
        self.summary_label.setText(
            f'Total Budget: ${total_budget:,.2f}  |  Actual Spend: ${total_actual:,.2f}'
            f'  |  Variance: ${total_variance:,.2f}'
        )

        self._rerender_chart(-1)

    def _on_include_toggled(self, name, state):
        self._included[name] = (state == Qt.Checked.value if hasattr(Qt.Checked, 'value') else bool(state))
        self._rerender_chart(self._hovered_row if self._hovered_row >= 0 else self._selected_row())

    # ── Chart rendering ───────────────────────────────────────────────────────
    def _rerender_chart(self, highlight_row=-1):
        rows = self._display_rows
        month = self.month_combo.currentData()
        if not rows or not month:
            self.chart_label.clear()
            return

        # Only plot included rows, preserving their order
        visible = [(i, r) for i, r in enumerate(rows) if self._included.get(r[0], True)]
        if not visible:
            self.chart_label.clear()
            return

        n = len(visible)
        fig, ax = plt.subplots(figsize=(max(7, n * 0.85), 4), dpi=110)
        setup_dark_axes(ax)

        # Remove x-axis label and title completely
        ax.set_title('')
        ax.xaxis.label.set_visible(False)

        positions = list(range(n))
        xtick_labels = []

        for plot_idx, (orig_idx, row) in enumerate(visible):
            is_highlight = (orig_idx == highlight_row)
            alpha = 1.0 if (highlight_row < 0 or is_highlight) else 0.25
            edge_color = '#ffffff' if is_highlight else DK_GRID
            edge_lw = 1.8 if is_highlight else 0.5

            # Budget bar — wider, behind
            ax.bar(plot_idx, row[1], width=0.65, color=DK_BUDGET, alpha=alpha,
                   edgecolor=edge_color, linewidth=edge_lw, zorder=2)
            # Actual bar — narrower, in front
            ax.bar(plot_idx, row[2], width=0.35, color=DK_ACTUAL, alpha=alpha,
                   edgecolor=edge_color, linewidth=edge_lw, zorder=3)

            xtick_labels.append(row[0])

        ax.set_xticks(positions)
        ax.set_xticklabels(xtick_labels, rotation=40, ha='right', fontsize=8, color=DK_DIM)
        ax.tick_params(axis='x', pad=2)

        # Legend only — no title, no column headers
        legend_elements = [
            Patch(facecolor=DK_BUDGET, label='Budget'),
            Patch(facecolor=DK_ACTUAL, label='Actual'),
        ]
        ax.legend(handles=legend_elements, facecolor=DK_SURFACE, edgecolor=DK_GRID,
                  labelcolor=DK_TEXT, fontsize=9, loc='upper right')

        pane_w = self._chart_pane.width() if hasattr(self, '_chart_pane') and self._chart_pane.width() > 50 else 900
        pane_h = self._chart_pane.height() if hasattr(self, '_chart_pane') and self._chart_pane.height() > 50 else 370
        self.chart_label.setPixmap(
            fig_to_pixmap(fig).scaled(pane_w, pane_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    # ── Set budget dialog ─────────────────────────────────────────────────────
    def set_budget(self):
        month = self.month_combo.currentData()
        if not month:
            return
        category_names = [c.name for c in self.categories if not c.is_income]
        if not category_names:
            QMessageBox.information(self, 'No Categories', 'Create some expense categories first.')
            return
        cat_name, ok = QInputDialog.getItem(
            self, 'Select Category', 'Category:', category_names, 0, False
        )
        if not ok or not cat_name:
            return
        amount, ok = QInputDialog.getDouble(
            self, 'Budget Amount', f'Enter monthly budget for {cat_name}:',
            0.0, 0.0, 1_000_000.0, 2
        )
        if not ok:
            return
        cat = next(c for c in self.categories if c.name == cat_name)
        existing = (
            self.session.query(CategoryBudget)
            .filter(CategoryBudget.category_id == cat.id,
                    CategoryBudget.budget_month == month)
            .first()
        )
        if existing:
            existing.budget_amount = amount
        else:
            self.session.add(CategoryBudget(
                category_id=cat.id, budget_month=month, budget_amount=amount
            ))
        self.session.commit()
        self.refresh_data()
