from io import BytesIO
from datetime import date
from collections import defaultdict
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_agg import FigureCanvasAgg
import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QSplitter,
    QScrollArea, QFrame, QSizePolicy, QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QColor, QFont

from sqlalchemy import func, extract, case

from finance_tracker.data.db import SessionLocal
from finance_tracker.data.models import Transaction, Category, Account


# ─────────────────────────────────────────────────────────────────────────────
# Cyberpunk palette
# ─────────────────────────────────────────────────────────────────────────────
CP_BG        = '#0d0d1a'
CP_SURFACE   = '#12122a'
CP_GRID      = '#1e1e3a'
CP_TEXT      = '#e0e0ff'
CP_TEXT_DIM  = '#7070aa'
CP_CYAN      = '#00f5ff'
CP_MAGENTA   = '#ff00cc'
CP_YELLOW    = '#ffe600'
CP_GREEN     = '#39ff14'
CP_ORANGE    = '#ff6600'
CP_PURPLE    = '#bf00ff'
CP_PINK      = '#ff3399'
CP_TEAL      = '#00ffcc'
CP_RED       = '#ff2244'
CP_BLUE      = '#4488ff'

CP_CATEGORY_COLORS = [
    CP_CYAN, CP_MAGENTA, CP_YELLOW, CP_GREEN, CP_ORANGE,
    CP_PURPLE, CP_PINK, CP_TEAL, CP_RED, CP_BLUE,
    '#ff9900', '#00ccff', '#cc00ff', '#ffcc00', '#00ff88',
]

ACCOUNT_CARD_STYLE = """
QFrame {{
    background-color: {bg};
    border-radius: 6px;
    border: 1px solid {border};
    min-width: 140px;
    max-width: 200px;
    max-height: 52px;
}}
"""

ACCOUNT_SCROLL_STYLE = """
QScrollArea { border: none; background: transparent; }
QScrollBar:horizontal { height: 5px; background: #0d0d1a; }
QScrollBar::handle:horizontal { background: #00f5ff; border-radius: 2px; }
"""

LEGEND_STYLE = """
QListWidget {
    background: #0d0d1a;
    border: 1px solid #1e1e3a;
    border-radius: 4px;
    color: #e0e0ff;
    font-size: 11px;
    outline: none;
}
QListWidget::item { padding: 3px 6px; border-radius: 3px; }
QListWidget::item:hover { background: #1e1e3a; color: #00f5ff; }
QListWidget::item:selected { background: #1e1e3a; color: #00f5ff; }
"""


def setup_cp_axes(ax):
    ax.set_facecolor(CP_SURFACE)
    ax.figure.patch.set_facecolor(CP_BG)
    ax.tick_params(colors=CP_TEXT_DIM, labelsize=8)
    ax.xaxis.label.set_color(CP_TEXT_DIM)
    ax.yaxis.label.set_color(CP_TEXT_DIM)
    ax.title.set_color(CP_CYAN)
    for spine in ax.spines.values():
        spine.set_edgecolor(CP_GRID)
    ax.grid(color=CP_GRID, linewidth=0.5, linestyle='--')
    ax.set_axisbelow(True)


def effective_date_expr():
    return func.coalesce(Transaction.post_date, Transaction.transaction_date)


def fig_to_pixmap(fig):
    buf = BytesIO()
    fig.tight_layout(pad=1.2)
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


def get_current_balance(session, account):
    tx_sum = session.query(func.sum(Transaction.amount)).filter(
        Transaction.account_id == account.account_id
    ).scalar()
    return float(account.starting_balance or 0) + float(tx_sum or 0)


# ─────────────────────────────────────────────────────────────────────────────
# Account balance card
# ─────────────────────────────────────────────────────────────────────────────
class AccountBalanceCard(QFrame):
    def __init__(self, name, balance, parent=None):
        super().__init__(parent)
        positive = balance >= 0
        bg = "#0d1a0d" if positive else "#1a0d0d"
        border = "#39ff14" if positive else "#ff2244"
        self.setStyleSheet(ACCOUNT_CARD_STYLE.format(bg=bg, border=border))
        layout = QHBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 4, 8, 4)
        name_label = QLabel(name)
        name_label.setStyleSheet("font-size: 11px; color: #7070aa; font-weight: bold;")
        name_label.setWordWrap(False)
        balance_label = QLabel(f"${balance:,.2f}")
        balance_label.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {'#39ff14' if positive else '#ff2244'};"
        )
        layout.addWidget(name_label)
        layout.addWidget(balance_label)


# ─────────────────────────────────────────────────────────────────────────────
# Chart + Legend panel
# ─────────────────────────────────────────────────────────────────────────────
class ChartLegendPanel(QWidget):
    """Holds a chart pixmap label on the left and a scrollable legend list on the right."""

    def __init__(self, title="", legend_width=180, parent=None):
        super().__init__(parent)
        self.title = title
        self._legend_items = []   # list of (label_str, color_hex)
        self._highlight_idx = None
        self._render_fn = None    # callable(highlight_idx) -> QPixmap

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.chart_label = QLabel()
        self.chart_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.chart_label, 1)

        right = QVBoxLayout()
        right.setSpacing(2)
        right.setContentsMargins(0, 0, 0, 0)

        legend_title = QLabel(title)
        legend_title.setStyleSheet(f"font-size: 11px; color: {CP_CYAN}; font-weight: bold;")
        right.addWidget(legend_title)

        self.legend_list = QListWidget()
        self.legend_list.setStyleSheet(LEGEND_STYLE)
        self.legend_list.setFixedWidth(legend_width)
        self.legend_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.legend_list.setFocusPolicy(Qt.NoFocus)
        self.legend_list.setMouseTracking(True)
        self.legend_list.itemEntered.connect(self._on_item_entered)
        self.legend_list.viewport().installEventFilter(self)
        right.addWidget(self.legend_list, 1)

        right_widget = QWidget()
        right_widget.setLayout(right)
        right_widget.setFixedWidth(legend_width + 4)
        layout.addWidget(right_widget)

    def eventFilter(self, source, event):
        from PySide6.QtCore import QEvent
        if source is self.legend_list.viewport() and event.type() == QEvent.Type.Leave:
            self._highlight_idx = None
            self._rerender()
        return super().eventFilter(source, event)

    def set_legend(self, items):
        """items: list of (label, color_hex)"""
        self._legend_items = items
        self.legend_list.clear()
        for label, color in items:
            item = QListWidgetItem(f"  {label}")
            swatch = QPixmap(12, 12)
            swatch.fill(QColor(color))
            item.setIcon(swatch if False else item.icon())  # use text color indicator
            item.setForeground(QColor(color))
            item.setFont(QFont("Consolas", 10))
            self.legend_list.addItem(item)

    def set_render_fn(self, fn):
        self._render_fn = fn

    def set_pixmap(self, pixmap):
        self.chart_label.setPixmap(pixmap)

    def _on_item_entered(self, item):
        idx = self.legend_list.row(item)
        self._highlight_idx = idx
        self._rerender()

    def _rerender(self):
        if self._render_fn:
            px = self._render_fn(self._highlight_idx)
            self.chart_label.setPixmap(px)


# ─────────────────────────────────────────────────────────────────────────────
# Monthly View
# ─────────────────────────────────────────────────────────────────────────────
class MonthlyView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = SessionLocal()
        self._cat_rows = []
        self._selected_month = None
        self._trend_labels = []
        self._trend_incomes = []
        self._trend_expenses = []
        self._trend_nets = []
        self._networth_values = []
        self.setup_ui()
        self.load_months()
        self.refresh_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(12, 8, 12, 8)

        title = QLabel('Monthly Analytics')
        title.setStyleSheet(f'font-size: 18px; font-weight: bold; color: {CP_CYAN};')
        title.setFixedHeight(28)
        layout.addWidget(title)

        # ── Account Balance Banner ────────────────────────────────────────
        banner_container = QWidget()
        banner_container.setStyleSheet(f"background: {CP_BG}; border-radius: 6px; border: 1px solid {CP_GRID};")
        banner_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        banner_container.setFixedHeight(80)
        banner_outer = QVBoxLayout(banner_container)
        banner_outer.setContentsMargins(6, 4, 6, 4)
        banner_outer.setSpacing(2)

        banner_title = QLabel("Account Balances")
        banner_title.setStyleSheet(f"font-size: 10px; color: {CP_TEXT_DIM}; font-weight: bold;")
        banner_title.setFixedHeight(14)
        banner_outer.addWidget(banner_title)

        self.balance_scroll = QScrollArea()
        self.balance_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.balance_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.balance_scroll.setStyleSheet(ACCOUNT_SCROLL_STYLE)
        self.balance_scroll.setFixedHeight(56)
        self.balance_scroll.setWidgetResizable(True)

        self.balance_scroll_inner = QWidget()
        self.balance_cards_layout = QHBoxLayout(self.balance_scroll_inner)
        self.balance_cards_layout.setSpacing(8)
        self.balance_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.balance_cards_layout.addStretch()
        self.balance_scroll.setWidget(self.balance_scroll_inner)

        banner_outer.addWidget(self.balance_scroll)
        layout.addWidget(banner_container)

        # ── Month Selector ────────────────────────────────────────────────
        top = QHBoxLayout()
        top.addWidget(QLabel('Month:'))
        self.month_combo = QComboBox()
        self.month_combo.setStyleSheet(f"background: {CP_SURFACE}; color: {CP_TEXT}; border: 1px solid {CP_GRID};")
        self.month_combo.currentIndexChanged.connect(self.refresh_data)
        top.addWidget(self.month_combo)
        top.addStretch()
        layout.addLayout(top)

        self.summary_label = QLabel('')
        self.summary_label.setStyleSheet(f'font-size: 12px; color: {CP_TEXT_DIM};')
        layout.addWidget(self.summary_label)

        # ── Scroll area for all chart rows ────────────────────────────────
        charts_scroll = QScrollArea()
        charts_scroll.setWidgetResizable(True)
        charts_scroll.setStyleSheet(f"QScrollArea {{ background: {CP_BG}; border: none; }}")

        charts_container = QWidget()
        charts_container.setStyleSheet(f"background: {CP_BG};")
        charts_vbox = QVBoxLayout(charts_container)
        charts_vbox.setSpacing(10)
        charts_vbox.setContentsMargins(0, 0, 0, 0)

        # Row 1: waterfall + category pie
        row1 = QHBoxLayout()
        self.waterfall_panel = ChartLegendPanel("Income vs Expense", legend_width=160)
        self.category_panel = ChartLegendPanel("Spending by Category", legend_width=200)
        row1.addWidget(self.waterfall_panel)
        row1.addWidget(self.category_panel)
        charts_vbox.addLayout(row1)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet(f"color: {CP_GRID};")
        charts_vbox.addWidget(div)

        # Row 2: cash flow trend + net worth trend
        row2 = QHBoxLayout()
        self.cashflow_panel = ChartLegendPanel("Cash Flow Trend", legend_width=160)
        self.networth_panel = ChartLegendPanel("Net Worth Trend", legend_width=160)
        row2.addWidget(self.cashflow_panel)
        row2.addWidget(self.networth_panel)
        charts_vbox.addLayout(row2)

        # Row 3: category table + recurring table
        row3 = QHBoxLayout()
        self.category_table = QTableWidget()
        self.category_table.setColumnCount(4)
        self.category_table.setHorizontalHeaderLabels(['Category', 'Actual Spend', 'Txn Count', 'Share'])
        self.category_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.category_table.verticalHeader().setVisible(False)
        self.category_table.setStyleSheet(f"background: {CP_SURFACE}; color: {CP_TEXT}; gridline-color: {CP_GRID};")

        self.recurring_table = QTableWidget()
        self.recurring_table.setColumnCount(6)
        self.recurring_table.setHorizontalHeaderLabels(['Recurring Candidate', 'Occurrences', 'Avg Amount', 'First Seen', 'Last Seen', 'Span Months'])
        self.recurring_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.recurring_table.verticalHeader().setVisible(False)
        self.recurring_table.setStyleSheet(f"background: {CP_SURFACE}; color: {CP_TEXT}; gridline-color: {CP_GRID};")

        row3.addWidget(self.category_table)
        row3.addWidget(self.recurring_table)
        charts_vbox.addLayout(row3)

        charts_scroll.setWidget(charts_container)
        layout.addWidget(charts_scroll, 1)

    # ── Banner ────────────────────────────────────────────────────────────────
    def _refresh_account_banner(self):
        while self.balance_cards_layout.count() > 1:
            item = self.balance_cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        accounts = self.session.query(Account).order_by(Account.account_name).all()
        total = 0.0
        for acc in accounts:
            bal = get_current_balance(self.session, acc)
            total += bal
            card = AccountBalanceCard(acc.account_name, bal)
            self.balance_cards_layout.insertWidget(self.balance_cards_layout.count() - 1, card)

        total_card = AccountBalanceCard("TOTAL", total)
        total_card.setStyleSheet(
            ACCOUNT_CARD_STYLE.format(bg="#0d0d2a", border=CP_CYAN) +
            f"QFrame {{ border: 1px solid {CP_CYAN}; }}"
        )
        self.balance_cards_layout.insertWidget(self.balance_cards_layout.count() - 1, total_card)

    # ── Month loading ─────────────────────────────────────────────────────────
    def load_months(self):
        cur = self.month_combo.currentData()
        self.month_combo.blockSignals(True)
        self.month_combo.clear()
        eff = effective_date_expr()
        rows = (
            self.session.query(
                extract('year', eff).label('yr'),
                extract('month', eff).label('mo')
            )
            .group_by('yr', 'mo')
            .order_by(extract('year', eff).desc(), extract('month', eff).desc())
            .all()
        )
        for r in rows:
            d = date(int(r.yr), int(r.mo), 1)
            self.month_combo.addItem(d.strftime('%Y-%m'), d)
        if cur:
            idx = self.month_combo.findData(cur)
            if idx >= 0:
                self.month_combo.setCurrentIndex(idx)
        self.month_combo.blockSignals(False)

    # ── Main refresh ──────────────────────────────────────────────────────────
    def refresh_data(self):
        self.session.expire_all()
        self._refresh_account_banner()

        selected_month = self.month_combo.currentData()
        if not selected_month:
            self.summary_label.setText('No transaction months available.')
            return
        self._selected_month = selected_month

        eff = effective_date_expr()
        start = date(selected_month.year, selected_month.month, 1)
        if selected_month.month == 12:
            end = date(selected_month.year + 1, 1, 1)
        else:
            end = date(selected_month.year, selected_month.month + 1, 1)

        tx_rows = (
            self.session.query(Transaction, Category)
            .outerjoin(Category, Transaction.category_id == Category.id)
            .filter(eff >= start)
            .filter(eff < end)
            .all()
        )

        income = sum(float(tx.Transaction.amount) for tx in tx_rows if float(tx.Transaction.amount) > 0)
        expenses = sum(abs(float(tx.Transaction.amount)) for tx in tx_rows if float(tx.Transaction.amount) < 0)
        net = income - expenses

        self.summary_label.setText(
            f'Income: ${income:,.2f}  |  Expenses: ${expenses:,.2f}  |  Net: ${net:,.2f}  |  Transactions: {len(tx_rows)}'
        )

        # Category breakdown
        cat_map = defaultdict(lambda: {'amount': 0.0, 'count': 0})
        recurring_map = defaultdict(list)
        for tx, cat in tx_rows:
            amt = float(tx.amount)
            if amt < 0:
                name = cat.name if cat else 'Uncategorized'
                cat_map[name]['amount'] += abs(amt)
                cat_map[name]['count'] += 1
            merchant_key = normalize_merchant(tx.merchant or tx.description)
            recurring_map[merchant_key].append(tx)

        self._cat_rows = sorted(cat_map.items(), key=lambda x: x[1]['amount'], reverse=True)

        # Category table
        self.category_table.setRowCount(len(self._cat_rows))
        total_spend = sum(v['amount'] for _, v in self._cat_rows) or 1.0
        for i, (name, info) in enumerate(self._cat_rows):
            self.category_table.setItem(i, 0, QTableWidgetItem(name))
            amt_item = QTableWidgetItem(f"${info['amount']:,.2f}")
            amt_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.category_table.setItem(i, 1, amt_item)
            self.category_table.setItem(i, 2, QTableWidgetItem(str(info['count'])))
            self.category_table.setItem(i, 3, QTableWidgetItem(f"{(info['amount']/total_spend)*100:,.1f}%"))
        self.category_table.resizeColumnsToContents()

        # Recurring table
        recurring_candidates = []
        for merchant, items in recurring_map.items():
            if len(items) >= 2:
                amounts = [abs(float(t.amount)) for t in items]
                dates_list = [(t.post_date or t.transaction_date) for t in items if (t.post_date or t.transaction_date)]
                if not dates_list:
                    continue
                days = [d.day for d in dates_list]
                first_seen = min(dates_list)
                last_seen = max(dates_list)
                span = max(1, (last_seen.year - first_seen.year) * 12 + (last_seen.month - first_seen.month) + 1)
                recurring_candidates.append((merchant, len(items), sum(amounts)/len(amounts), round(sum(days)/len(days)), last_seen, span))
        recurring_candidates.sort(key=lambda x: (-x[1], x[0]))

        self.recurring_table.setRowCount(len(recurring_candidates))
        for i, row in enumerate(recurring_candidates):
            vals = [row[0], str(row[1]), f"${row[2]:,.2f}", str(row[3]), row[4].isoformat(), str(row[5])]
            for j, val in enumerate(vals):
                self.recurring_table.setItem(i, j, QTableWidgetItem(val))
        self.recurring_table.resizeColumnsToContents()

        # Trend data (all months)
        trend_rows = (
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
        self._trend_labels = [f"{int(r.yr):04d}-{int(r.mo):02d}" for r in trend_rows]
        self._trend_incomes = [float(r.income or 0) for r in trend_rows]
        self._trend_expenses = [float(r.expense or 0) for r in trend_rows]
        self._trend_nets = [float(r.net or 0) for r in trend_rows]

        # Net worth data
        accounts = self.session.query(Account).all()
        self._networth_values = []
        for label in self._trend_labels:
            y, m = map(int, label.split('-'))
            total_nw = 0.0
            for acc in accounts:
                total_nw += float(acc.starting_balance or 0)
                d1 = self.session.query(func.sum(Transaction.amount)).filter(
                    Transaction.account_id == acc.account_id,
                    extract('year', eff) < y
                ).scalar()
                total_nw += float(d1 or 0)
                d2 = self.session.query(func.sum(Transaction.amount)).filter(
                    Transaction.account_id == acc.account_id,
                    extract('year', eff) == y,
                    extract('month', eff) <= m,
                ).scalar()
                total_nw += float(d2 or 0)
            self._networth_values.append(total_nw)

        self._render_waterfall(income, expenses, net)
        self._render_category_pie()
        self._render_cashflow()
        self._render_networth()

    # ── Waterfall chart ───────────────────────────────────────────────────────
    def _make_waterfall(self, highlight=None):
        income = float(self.summary_label.text().split('$')[1].replace(',', '').split()[0]) if '$' in self.summary_label.text() else 0
        # Re-parse from label text is fragile; store values directly
        return self._waterfall_pixmap_fn(highlight)

    def _render_waterfall(self, income, expenses, net):
        self._wf_values = (income, expenses, net)

        def make(highlight=None):
            labels = ['Income', 'Expenses', 'Net']
            values = [income, expenses, net]
            base_colors = [CP_GREEN, CP_RED, CP_CYAN]
            colors = []
            for i, c in enumerate(base_colors):
                if highlight is None or i == highlight:
                    colors.append(c)
                else:
                    colors.append('#333355')

            fig, ax = plt.subplots(figsize=(6, 3.5), dpi=110)
            setup_cp_axes(ax)
            bars = ax.bar(labels, [income, expenses, net], color=colors,
                          edgecolor=CP_GRID, linewidth=0.8, width=0.5)
            ax.axhline(0, color=CP_TEXT_DIM, linewidth=0.8)
            ax.set_title('Income vs Expense', color=CP_CYAN, fontsize=10)
            max_abs = max(abs(v) for v in [income, expenses, net]) or 1
            for i, (b, v) in enumerate(zip(bars, [income, expenses, net])):
                c = colors[i] if colors[i] != '#333355' else CP_TEXT_DIM
                offset = max_abs * 0.04 if v >= 0 else -max_abs * 0.1
                ax.text(b.get_x() + b.get_width()/2, v + offset,
                        f'${abs(v):,.0f}', ha='center', fontsize=8, color=c)
            return fig_to_pixmap(fig).scaled(580, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        self.waterfall_panel.set_render_fn(make)
        self.waterfall_panel.set_pixmap(make())
        self.waterfall_panel.set_legend([
            ('Income', CP_GREEN), ('Expenses', CP_RED), ('Net', CP_CYAN)
        ])

    # ── Category pie ──────────────────────────────────────────────────────────
    def _render_category_pie(self):
        cat_rows = self._cat_rows
        if not cat_rows:
            fig, ax = plt.subplots(figsize=(6, 3.5), dpi=110)
            setup_cp_axes(ax)
            ax.text(0.5, 0.5, 'No expense data', ha='center', va='center', color=CP_TEXT_DIM)
            ax.axis('off')
            self.category_panel.set_pixmap(fig_to_pixmap(fig).scaled(580, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            return

        top_rows = cat_rows[:12]
        names = [n for n, _ in top_rows]
        values = [v['amount'] for _, v in top_rows]
        colors_base = CP_CATEGORY_COLORS[:len(names)]
        legend_items = list(zip(names, colors_base))

        def make(highlight=None):
            alphas = []
            edge_widths = []
            for i in range(len(names)):
                if highlight is None or i == highlight:
                    alphas.append(1.0)
                    edge_widths.append(2.0 if i == highlight else 0.5)
                else:
                    alphas.append(0.25)
                    edge_widths.append(0.3)

            fig, ax = plt.subplots(figsize=(6, 3.5), dpi=110)
            fig.patch.set_facecolor(CP_BG)
            ax.set_facecolor(CP_BG)
            wedges, texts, autotexts = ax.pie(
                values,
                labels=None,
                autopct='%1.1f%%',
                startangle=90,
                colors=colors_base,
                wedgeprops={'linewidth': 0.5, 'edgecolor': CP_BG},
                pctdistance=0.78,
            )
            for i, (w, at) in enumerate(zip(wedges, autotexts)):
                w.set_alpha(alphas[i])
                w.set_linewidth(edge_widths[i])
                at.set_color(CP_BG)
                at.set_fontsize(7)
                if highlight == i:
                    w.set_edgecolor(CP_YELLOW)
                    w.set_linewidth(2.5)
            ax.set_title('Spending by Category', color=CP_CYAN, fontsize=10)
            return fig_to_pixmap(fig).scaled(580, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        self.category_panel.set_render_fn(make)
        self.category_panel.set_pixmap(make())
        self.category_panel.set_legend(legend_items)

    # ── Cash flow trend ───────────────────────────────────────────────────────
    def _render_cashflow(self):
        labels = self._trend_labels
        incomes = self._trend_incomes
        expenses = self._trend_expenses
        nets = self._trend_nets

        series = [
            ('Income', incomes, CP_GREEN, 'o'),
            ('Expenses', expenses, CP_MAGENTA, 's'),
            ('Net Cash Flow', nets, CP_CYAN, '^'),
        ]
        legend_items = [(s[0], s[2]) for s in series]

        def make(highlight=None):
            fig, ax = plt.subplots(figsize=(6, 3.5), dpi=110)
            setup_cp_axes(ax)
            if labels:
                for i, (name, data, color, marker) in enumerate(series):
                    alpha = 1.0 if (highlight is None or i == highlight) else 0.15
                    lw = 2.5 if i == highlight else 1.5
                    if i == 2:  # Net as bar
                        bar_colors = [CP_CYAN if v >= 0 else CP_RED for v in data]
                        bar_alpha = alpha
                        ax.bar(labels, data, color=bar_colors, alpha=bar_alpha * 0.4,
                               label=name if highlight is None or i == highlight else '_')
                    else:
                        ax.plot(labels, data, marker=marker, label=name,
                                color=color, linewidth=lw, alpha=alpha,
                                markersize=5 if i == highlight else 4)
                ax.tick_params(axis='x', rotation=45, labelsize=7)
            else:
                ax.text(0.5, 0.5, 'No data', ha='center', va='center', color=CP_TEXT_DIM)
                ax.axis('off')
            ax.set_title('Monthly Cash Flow Trend', color=CP_CYAN, fontsize=10)
            return fig_to_pixmap(fig).scaled(580, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        self.cashflow_panel.set_render_fn(make)
        self.cashflow_panel.set_pixmap(make())
        self.cashflow_panel.set_legend(legend_items)

    # ── Net worth trend ───────────────────────────────────────────────────────
    def _render_networth(self):
        labels = self._trend_labels
        values = self._networth_values

        accounts = self.session.query(Account).order_by(Account.account_name).all()
        acc_colors = CP_CATEGORY_COLORS[:len(accounts)]
        legend_items = [('Net Worth', CP_PURPLE)] + list(zip([a.account_name for a in accounts], acc_colors))

        def make(highlight=None):
            fig, ax = plt.subplots(figsize=(6, 3.5), dpi=110)
            setup_cp_axes(ax)
            if labels:
                nw_alpha = 1.0 if (highlight is None or highlight == 0) else 0.15
                nw_lw = 2.5 if highlight == 0 else 2.0
                ax.plot(labels, values, marker='o', color=CP_PURPLE,
                        linewidth=nw_lw, alpha=nw_alpha, markersize=5, label='Net Worth')
                ax.fill_between(range(len(labels)), values,
                                alpha=nw_alpha * 0.15, color=CP_PURPLE)

                eff = effective_date_expr()
                for ai, acc in enumerate(accounts):
                    acc_values = []
                    for label in labels:
                        y, m = map(int, label.split('-'))
                        base = float(acc.starting_balance or 0)
                        d1 = self.session.query(func.sum(Transaction.amount)).filter(
                            Transaction.account_id == acc.account_id,
                            extract('year', eff) < y
                        ).scalar()
                        d2 = self.session.query(func.sum(Transaction.amount)).filter(
                            Transaction.account_id == acc.account_id,
                            extract('year', eff) == y,
                            extract('month', eff) <= m,
                        ).scalar()
                        acc_values.append(base + float(d1 or 0) + float(d2 or 0))

                    series_idx = ai + 1
                    alpha = 1.0 if (highlight is None or highlight == series_idx) else 0.15
                    lw = 2.5 if highlight == series_idx else 1.2
                    color = acc_colors[ai]
                    ax.plot(labels, acc_values, marker='.', color=color,
                            linewidth=lw, alpha=alpha, markersize=4,
                            label=acc.account_name, linestyle='--')

                ax.set_xticks(range(len(labels)))
                ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=7)
            else:
                ax.text(0.5, 0.5, 'No data', ha='center', va='center', color=CP_TEXT_DIM)
                ax.axis('off')
            ax.set_title('Estimated Net Worth Trend', color=CP_CYAN, fontsize=10)
            return fig_to_pixmap(fig).scaled(580, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        self.networth_panel.set_render_fn(make)
        self.networth_panel.set_pixmap(make())
        self.networth_panel.set_legend(legend_items)
