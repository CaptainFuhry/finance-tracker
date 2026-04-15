# finance_tracker/ui/import_wizard.py

import os
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QGroupBox,
    QFormLayout,
    QCheckBox,
    QScrollArea,
    QWidget,
    QLineEdit,
    QMessageBox,
    QAbstractItemView,
    QSizePolicy,
    QFrame,
)
from PySide6.QtCore import Qt

from finance_tracker.data.db import SessionLocal
from finance_tracker.data.models import Account
from finance_tracker.services.schema_profile_service import SchemaProfileService
from finance_tracker.services.import_service import ImportService


FIELD_LABELS = [
    ("date_col",         "Transaction Date Column *"),
    ("post_date_col",    "Posted Date Column"),
    ("description_col",  "Description Column *"),
    ("amount_col",       "Amount Column (single)"),
    ("debit_col",        "Debit Column (split)"),
    ("credit_col",       "Credit Column (split)"),
]


class ImportWizardDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Transactions")
        self.setMinimumSize(860, 720)

        self.filepath = None
        self.headers = []
        self.ignored_cols = set()
        self.column_combos = {}
        self.ignore_checkboxes = {}

        # ── Saved step values — persisted across layout clears ──
        self._selected_account_id = None
        self._selected_account_name = ""
        self._selected_schema_id = None
        self._profile_name = ""
        self._col_mapping = {}   # field_key → selected column value

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(8)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self._build_step1()

    # ── Step 1 ───────────────────────────────────────────────────────────────

    def _build_step1(self):
        self._clear_layout()

        self.main_layout.addWidget(QLabel("<b>Step 1 — Select File and Account</b>"))

        file_group = QGroupBox("Statement File")
        file_layout = QHBoxLayout(file_group)
        self.filepath_label = QLabel(
            os.path.basename(self.filepath) if self.filepath else "No file selected."
        )
        self.filepath_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_file)
        file_layout.addWidget(self.filepath_label)
        file_layout.addWidget(browse_btn)
        self.main_layout.addWidget(file_group)

        account_group = QGroupBox("Account")
        account_layout = QFormLayout(account_group)
        self.account_combo = QComboBox()
        self.account_combo.currentIndexChanged.connect(self._on_account_changed)
        self._load_accounts()
        # Restore previous selection if navigating back
        if self._selected_account_id is not None:
            idx = self.account_combo.findData(self._selected_account_id)
            if idx >= 0:
                self.account_combo.setCurrentIndex(idx)
        account_layout.addRow("Account:", self.account_combo)
        self.main_layout.addWidget(account_group)

        schema_group = QGroupBox("Schema Profile")
        schema_layout = QFormLayout(schema_group)
        self.schema_combo = QComboBox()
        self.schema_combo.addItem("(auto-detect / create new)", None)
        for p in SchemaProfileService.get_all():
            self.schema_combo.addItem(p.name, p.id)
        # Restore previous schema selection if navigating back
        if self._selected_schema_id is not None:
            idx = self.schema_combo.findData(self._selected_schema_id)
            if idx >= 0:
                self.schema_combo.setCurrentIndex(idx)
        schema_layout.addRow("Saved Profile:", self.schema_combo)
        self.main_layout.addWidget(schema_group)

        self.main_layout.addStretch()
        nav = self._nav_buttons(back=False, next_fn=self._go_step2)
        self.main_layout.addLayout(nav)

    def _load_accounts(self):
        self.account_combo.clear()
        session = SessionLocal()
        try:
            accounts = session.query(Account).order_by(Account.account_name).all()
            for acc in accounts:
                self.account_combo.addItem(acc.account_name, acc.account_id)
        finally:
            session.close()

    def _on_account_changed(self):
        account_id = self.account_combo.currentData()
        if account_id is None:
            return
        last_profile = SchemaProfileService.get_last_used_for_account(account_id)
        if last_profile:
            idx = self.schema_combo.findData(last_profile.id)
            if idx >= 0:
                self.schema_combo.setCurrentIndex(idx)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Statement File", "", "CSV Files (*.csv);;All Files (*)"
        )
        if path:
            self.filepath = path
            self.filepath_label.setText(os.path.basename(path))

    def _go_step2(self):
        if not self.filepath:
            QMessageBox.warning(self, "No File", "Please select a statement file.")
            return
        if self.account_combo.currentData() is None:
            QMessageBox.warning(self, "No Account", "Please select an account.")
            return

        # ── Save Step 1 selections to instance variables BEFORE clearing ──
        self._selected_account_id = self.account_combo.currentData()
        self._selected_account_name = self.account_combo.currentText()
        self._selected_schema_id = self.schema_combo.currentData()

        try:
            self.headers = ImportService.read_csv_headers(self.filepath)
        except Exception as e:
            QMessageBox.critical(self, "File Error", str(e))
            return
        self._build_step2()

    # ── Step 2 ───────────────────────────────────────────────────────────────

    def _build_step2(self):
        self._clear_layout()
        self.main_layout.addWidget(QLabel("<b>Step 2 — Map Columns</b>"))

        hint = QLabel("Map your CSV columns to the required fields. Check 'Ignore' for columns you do not want to import.")
        hint.setWordWrap(True)
        self.main_layout.addWidget(hint)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        saved_profile = None
        if self._selected_schema_id:
            saved_profile = SchemaProfileService.get_by_id(self._selected_schema_id)

        def profile_val(attr):
            if saved_profile:
                return getattr(saved_profile, attr, None)
            return None

        mapping_group = QGroupBox("Field Mapping")
        mapping_layout = QFormLayout(mapping_group)

        field_map = {
            "date_col":        "date_column",
            "post_date_col":   "post_date_column",
            "description_col": "description_column",
            "amount_col":      "amount_column",
            "debit_col":       "debit_column",
            "credit_col":      "credit_column",
        }

        self.column_combos = {}
        for field_key, label in FIELD_LABELS:
            combo = QComboBox()
            combo.addItem("(none)", None)
            for h in self.headers:
                combo.addItem(h, h)

            # Restore from previous Step 2 visit if navigating back
            if field_key in self._col_mapping and self._col_mapping[field_key]:
                idx = combo.findData(self._col_mapping[field_key])
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            else:
                pval = profile_val(field_map[field_key])
                if pval:
                    idx = combo.findData(pval)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                    else:
                        for i in range(combo.count()):
                            if combo.itemText(i).lower() == pval.lower():
                                combo.setCurrentIndex(i)
                                break

            self.column_combos[field_key] = combo
            mapping_layout.addRow(label, combo)

        scroll_layout.addWidget(mapping_group)

        ignore_group = QGroupBox("Ignore Columns")
        ignore_layout = QVBoxLayout(ignore_group)
        self.ignore_checkboxes = {}
        for h in self.headers:
            cb = QCheckBox(h)
            # Restore ignored state if navigating back
            if h in self.ignored_cols:
                cb.setChecked(True)
            self.ignore_checkboxes[h] = cb
            ignore_layout.addWidget(cb)

        scroll_layout.addWidget(ignore_group)
        scroll_area.setWidget(scroll_content)
        self.main_layout.addWidget(scroll_area)

        profile_form = QGroupBox("Save as Profile")
        pf_layout = QFormLayout(profile_form)
        self.profile_name_input = QLineEdit()
        if self._profile_name:
            self.profile_name_input.setText(self._profile_name)
        elif saved_profile:
            self.profile_name_input.setText(saved_profile.name)
        else:
            self.profile_name_input.setText(self._selected_account_name)
        pf_layout.addRow("Profile Name:", self.profile_name_input)
        self.main_layout.addWidget(profile_form)

        nav = self._nav_buttons(back_fn=self._build_step1, next_fn=self._go_step3)
        self.main_layout.addLayout(nav)

    def _go_step3(self):
        if not self.column_combos.get("date_col") or self.column_combos["date_col"].currentData() is None:
            QMessageBox.warning(self, "Mapping Error", "Transaction Date column is required.")
            return
        if self.column_combos.get("description_col") and self.column_combos["description_col"].currentData() is None:
            QMessageBox.warning(self, "Mapping Error", "Description column is required.")
            return

        # ── Save Step 2 selections BEFORE clearing ──
        self._col_mapping = {k: combo.currentData() for k, combo in self.column_combos.items()}
        self._ignored_cols = {h for h, cb in self.ignore_checkboxes.items() if cb.isChecked()}
        self._profile_name = self.profile_name_input.text().strip()

        self.ignored_cols = self._ignored_cols
        self._build_step3()

    # ── Step 3: Preview ──────────────────────────────────────────────────────

    def _build_step3(self):
        self._clear_layout()

        self.main_layout.addWidget(QLabel("<b>Step 3 — Preview (first 5 rows)</b>"))

        try:
            preview_rows = ImportService.preview_rows(self.filepath, max_rows=5)
        except Exception as e:
            QMessageBox.critical(self, "Preview Error", str(e))
            return

        visible_headers = [h for h in self.headers if h not in self.ignored_cols]

        table = QTableWidget()
        table.setColumnCount(len(visible_headers))
        table.setHorizontalHeaderLabels(visible_headers)
        table.setRowCount(len(preview_rows))
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        table.setFixedHeight(180)

        for row_idx, row in enumerate(preview_rows):
            for col_idx, h in enumerate(visible_headers):
                val = str(row.get(h, ""))
                table.setItem(row_idx, col_idx, QTableWidgetItem(val))

        table.resizeColumnsToContents()
        self.main_layout.addWidget(table)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        self.main_layout.addWidget(line)

        # ── Use saved instance variables — NOT combo box widgets ──
        amount_mode = (
            "single amount column"
            if self._col_mapping.get("amount_col")
            else "split debit / credit columns"
        )
        summary = QLabel(
            f"<b>File:</b> {os.path.basename(self.filepath)}<br>"
            f"<b>Account:</b> {self._selected_account_name}<br>"
            f"<b>Date column:</b> {self._col_mapping.get('date_col')}<br>"
            f"<b>Description column:</b> {self._col_mapping.get('description_col')}<br>"
            f"<b>Amount mode:</b> {amount_mode}<br>"
            f"<b>Ignored columns:</b> {', '.join(self.ignored_cols) if self.ignored_cols else 'none'}"
        )
        summary.setWordWrap(True)
        self.main_layout.addWidget(summary)

        self.main_layout.addStretch()

        nav = self._nav_buttons(back_fn=self._build_step2, next_label="Import", next_fn=self._run_import)
        self.main_layout.addLayout(nav)

    # ── Import ───────────────────────────────────────────────────────────────

    def _run_import(self):
        # ── Read entirely from saved instance variables ──
        account_id = self._selected_account_id
        date_col = self._col_mapping.get("date_col")
        post_date_col = self._col_mapping.get("post_date_col")
        description_col = self._col_mapping.get("description_col")
        amount_col = self._col_mapping.get("amount_col")
        debit_col = self._col_mapping.get("debit_col")
        credit_col = self._col_mapping.get("credit_col")
        profile_name = self._profile_name

        profile_id = None
        if profile_name:
            profile_id, err = SchemaProfileService.create_or_update(
                name=profile_name,
                institution="",
                account_type="",
                date_column=date_col,
                post_date_column=post_date_col,
                description_column=description_col,
                amount_column=amount_col,
                debit_column=debit_col,
                credit_column=credit_col,
                balance_column=None,
                notes=None,
            )
            if not err and profile_id:
                SchemaProfileService.save_last_used_for_account(account_id, profile_id)

        batch_id, row_count, error = ImportService.import_transactions(
            filepath=self.filepath,
            account_id=account_id,
            schema_profile_id=profile_id,
            date_col=date_col,
            post_date_col=post_date_col,
            description_col=description_col,
            amount_col=amount_col,
            debit_col=debit_col,
            credit_col=credit_col,
            ignored_cols=self.ignored_cols,
            account_type="credit",
        )

        if error:
            QMessageBox.critical(self, "Import Failed", error)
            return

        QMessageBox.information(
            self,
            "Import Complete",
            f"{row_count} transactions imported successfully.\nBatch ID: {batch_id}",
        )
        self.accept()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _nav_buttons(self, back=True, back_fn=None, next_fn=None, next_label="Next →"):
        layout = QHBoxLayout()
        layout.addStretch()
        if back and back_fn:
            back_btn = QPushButton("← Back")
            back_btn.clicked.connect(back_fn)
            layout.addWidget(back_btn)
        if next_fn:
            next_btn = QPushButton(next_label)
            next_btn.clicked.connect(next_fn)
            layout.addWidget(next_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)
        return layout

    def _clear_layout(self):
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_sub_layout(item.layout())

    def _clear_sub_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()