# finance_tracker/ui/categories_view.py

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QMessageBox,
    QDialog, QFormLayout, QLineEdit, QComboBox, QDialogButtonBox,
    QHeaderView, QRadioButton, QCheckBox,
)
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QColor

from finance_tracker.data.db import SessionLocal
from finance_tracker.data.models import Category, Transaction
from finance_tracker.ui.account_filter_bar import AccountFilterBar
from sqlalchemy import func


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


# ── Dialog ────────────────────────────────────────────────────────────────────

class CategoryDialog(QDialog):
    """
    Add / Edit a category.

    Schema:
        id               INTEGER  PK
        name             VARCHAR(100)  NOT NULL  UNIQUE
        parent_category  VARCHAR(100)
        is_income        BOOLEAN
    """
    def __init__(self, parent=None, category=None, session=None):
        super().__init__(parent)
        self.session = session or SessionLocal()
        self.setWindowTitle("Category")
        self.setMinimumWidth(380)

        layout = QFormLayout(self)

        self.name_input   = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Groceries, Salary, Rent")

        # Parent category — dropdown of existing category names + blank
        self.parent_combo = QComboBox()
        self.parent_combo.addItem("(none)", "")
        existing = (
            self.session.query(Category.name)
            .order_by(Category.name)
            .all()
        )
        for (cat_name,) in existing:
            # Don't allow a category to be its own parent when editing
            if category and cat_name == category.name:
                continue
            self.parent_combo.addItem(cat_name, cat_name)

        self.is_income_check = QCheckBox("This is an income category")

        layout.addRow("Category Name:",   self.name_input)
        layout.addRow("Parent Category:", self.parent_combo)
        layout.addRow("",                 self.is_income_check)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        # Pre-fill when editing
        if category:
            self.name_input.setText(category.name or "")
            idx = self.parent_combo.findData(category.parent_category or "")
            if idx >= 0:
                self.parent_combo.setCurrentIndex(idx)
            self.is_income_check.setChecked(bool(category.is_income))

    def get_data(self):
        parent = self.parent_combo.currentData() or None  # "" → None
        return {
            "name":            self.name_input.text().strip(),
            "parent_category": parent,
            "is_income":       self.is_income_check.isChecked(),
        }


# ── Main view ─────────────────────────────────────────────────────────────────

class CategoriesView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.session                = SessionLocal()
        self._current_account_id   = None
        self._selected_category_id = None
        self._radio_buttons        = {}   # cat_id → QRadioButton
        self._row_to_cat_id        = {}   # row    → cat_id
        self._selected_rows        = set()
        self._anchor_row           = -1
        self.setup_ui()
        self.load_categories()

    # ── UI ────────────────────────────────────────────────────────────────────

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(12, 12, 12, 12)

        title = QLabel("Categories")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        main_layout.addWidget(title)

        self.filter_bar = AccountFilterBar()
        self.filter_bar.account_changed.connect(self._on_account_filter_changed)
        main_layout.addWidget(self.filter_bar)

        btn_row = QHBoxLayout()
        self.add_button    = QPushButton("Add Category")
        self.edit_button   = QPushButton("Edit Category")
        self.delete_button = QPushButton("Delete Category")
        btn_row.addWidget(self.add_button)
        btn_row.addWidget(self.edit_button)
        btn_row.addWidget(self.delete_button)
        btn_row.addStretch()
        main_layout.addLayout(btn_row)

        self.totals_label = QLabel("")
        self.totals_label.setStyleSheet("font-size: 13px; color: #aaaaaa;")
        main_layout.addWidget(self.totals_label)

        self.table = QTableWidget()
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "", "ID", "Category Name", "Parent Category", "Income?", "Total Spent",
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

        self.add_button.clicked.connect(self.add_category)
        self.edit_button.clicked.connect(self.edit_category)
        self.delete_button.clicked.connect(self.delete_category)

    # ── Event filter ──────────────────────────────────────────────────────────

    def eventFilter(self, source, event):
        if source is self.table.viewport() and event.type() == QEvent.Type.MouseButtonPress:
            index = self.table.indexAt(event.pos())
            if index.isValid():
                row  = index.row()
                mods = event.modifiers()

                print(f"[CAT] click row={row}  ctrl={bool(mods & Qt.ControlModifier)}  "
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

                print(f"[CAT]       after={sorted(self._selected_rows)}")
                self._sync_from_rows()
            return True
        return super().eventFilter(source, event)

    # ── Selection sync ────────────────────────────────────────────────────────

    def _sync_from_rows(self):
        anchor_cat_id = self._row_to_cat_id.get(self._anchor_row)
        self._selected_category_id = anchor_cat_id

        for cat_id, radio in self._radio_buttons.items():
            radio.blockSignals(True)
            radio.setChecked(cat_id == anchor_cat_id)
            radio.blockSignals(False)

        for row in range(self.table.rowCount()):
            bg = HIGHLIGHT_COLOR if row in self._selected_rows else NORMAL_COLOR
            for col in range(1, self.table.columnCount()):
                item = self.table.item(row, col)
                if item:
                    item.setBackground(bg)

    # ── Filter bar ────────────────────────────────────────────────────────────

    def _on_account_filter_changed(self, account_id):
        self._current_account_id = account_id
        self._selected_rows.clear()
        self._anchor_row = -1
        self.load_categories()

    # ── Load ─────────────────────────────────────────────────────────────────

    def load_categories(self):
        categories = self.session.query(Category).order_by(Category.name).all()

        tx_query = (
            self.session.query(
                Transaction.category_id,
                func.sum(Transaction.amount).label("total"),
            ).group_by(Transaction.category_id)
        )
        if self._current_account_id is not None:
            tx_query = tx_query.filter(
                Transaction.account_id == self._current_account_id)
        totals = {row.category_id: float(row.total) for row in tx_query.all()}

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self._radio_buttons = {}
        self._row_to_cat_id = {}
        self._selected_rows.clear()
        self._anchor_row = -1
        grand_total = 0.0

        for row_index, cat in enumerate(categories):
            self.table.insertRow(row_index)
            self._row_to_cat_id[row_index] = cat.id
            spent = totals.get(cat.id, 0.0)
            grand_total += spent

            # Col 0 — radio
            radio = QRadioButton()
            radio.setProperty("cat_id", cat.id)
            radio.setStyleSheet("margin-left: 8px;")
            radio.clicked.connect(self._on_radio_clicked)
            self._radio_buttons[cat.id] = radio
            self.table.setCellWidget(row_index, 0, radio)

            # Col 1 — id
            self.table.setItem(row_index, 1, QTableWidgetItem(str(cat.id)))

            # Col 2 — name
            self.table.setItem(row_index, 2, QTableWidgetItem(cat.name or ""))

            # Col 3 — parent_category
            self.table.setItem(row_index, 3,
                QTableWidgetItem(cat.parent_category or ""))

            # Col 4 — is_income
            income_text = "Yes" if cat.is_income else ""
            income_item = QTableWidgetItem(income_text)
            income_item.setTextAlignment(Qt.AlignCenter)
            if cat.is_income:
                income_item.setForeground(QColor("#4caf50"))
            self.table.setItem(row_index, 4, income_item)

            # Col 5 — total spent
            spent_item = QTableWidgetItem(f"${spent:,.2f}")
            spent_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            spent_item.setForeground(
                QColor("#f44336") if spent < 0 else
                QColor("#4caf50") if spent > 0 else
                QColor("#aaaaaa")
            )
            self.table.setItem(row_index, 5, spent_item)

        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, 36)
        self.table.setSortingEnabled(True)

        count        = len(categories)
        filter_label = ("all accounts" if self._current_account_id is None
                        else "selected account")
        color        = "#4caf50" if grand_total >= 0 else "#f44336"
        self.totals_label.setText(
            f"<b>{count}</b> categor{'ies' if count != 1 else 'y'}  |  "
            f"Net spending ({filter_label}): "
            f"<span style='color:{color};'><b>${grand_total:,.2f}</b></span>"
        )

    def _on_radio_clicked(self):
        cat_id = self.sender().property("cat_id")
        target_row = next(
            (r for r, cid in self._row_to_cat_id.items() if cid == cat_id), None)
        if target_row is None:
            return
        self._selected_rows = {target_row}
        self._anchor_row    = target_row
        self._sync_from_rows()

    def get_selected_category(self):
        if not self._selected_category_id:
            return None
        return self.session.query(Category).filter(
            Category.id == self._selected_category_id
        ).first()

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def add_category(self):
        dialog = CategoryDialog(self, session=self.session)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            if not data["name"]:
                QMessageBox.warning(self, "Validation Error",
                    "Category name is required.")
                return
            if self.session.query(Category).filter(
                Category.name == data["name"]
            ).first():
                QMessageBox.warning(self, "Duplicate",
                    f"A category named '{data['name']}' already exists.")
                return
            self.session.add(Category(
                name=data["name"],
                parent_category=data["parent_category"],
                is_income=data["is_income"],
            ))
            self.session.commit()
            self.load_categories()

    def edit_category(self):
        cat = self.get_selected_category()
        if not cat:
            QMessageBox.information(self, "Select Category",
                "Please select a category using the radio button.")
            return
        dialog = CategoryDialog(self, category=cat, session=self.session)
        if dialog.exec() == QDialog.Accepted:
            data = dialog.get_data()
            if not data["name"]:
                QMessageBox.warning(self, "Validation Error",
                    "Category name is required.")
                return
            cat.name            = data["name"]
            cat.parent_category = data["parent_category"]
            cat.is_income       = data["is_income"]
            self.session.commit()
            self.load_categories()

    def delete_category(self):
        cat = self.get_selected_category()
        if not cat:
            QMessageBox.information(self, "Select Category",
                "Please select a category using the radio button.")
            return
        tx_count = self.session.query(Transaction).filter(
            Transaction.category_id == cat.id
        ).count()
        msg = f"Delete category '{cat.name}'?"
        if tx_count > 0:
            msg += (f"\n\nWarning: {tx_count} transaction(s) will be "
                    f"set to uncategorized.")
        if QMessageBox.question(
            self, "Confirm Delete", msg,
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            self.session.query(Transaction).filter(
                Transaction.category_id == cat.id
            ).update({"category_id": None})
            self.session.delete(cat)
            self.session.commit()
            self.load_categories()