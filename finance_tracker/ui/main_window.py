from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QStackedWidget,
)

from finance_tracker.ui.accounts_view import AccountsView
from finance_tracker.ui.categories_view import CategoriesView
from finance_tracker.ui.transactions_view import TransactionsView
from finance_tracker.ui.import_wizard import ImportWizardDialog
from finance_tracker.ui.monthly_view import MonthlyView
from finance_tracker.ui.budgeting_view import BudgetingView


NAV_STYLE = """
QPushButton {
    text-align: left;
    padding: 8px 12px;
    border-radius: 4px;
    color: #e0e0ff;
}
QPushButton:hover {
    background-color: #1e1e3a;
    color: #00f5ff;
}
"""

IMPORT_BTN_STYLE = """
QPushButton {
    text-align: left;
    padding: 8px 12px;
    border-radius: 4px;
    color: #00f5ff;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #0d1a2a;
    color: #ffe600;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Finance Tracker")
        self.resize(1600, 950)

        container = QWidget()
        root = QHBoxLayout(container)

        nav = QVBoxLayout()
        nav.setSpacing(2)

        self.monthly_btn      = QPushButton("Monthly View")
        self.budgeting_btn    = QPushButton("Budgeting View")
        self.accounts_btn     = QPushButton("Accounts")
        self.import_btn       = QPushButton("Import Transactions")
        self.transactions_btn = QPushButton("Transactions")
        self.categories_btn   = QPushButton("Categories")

        for btn in [
            self.monthly_btn,
            self.budgeting_btn,
            self.accounts_btn,
            self.import_btn,
            self.transactions_btn,
            self.categories_btn,
        ]:
            btn.setStyleSheet(NAV_STYLE)
            nav.addWidget(btn)

        self.import_btn.setStyleSheet(IMPORT_BTN_STYLE)
        nav.addStretch()

        self.stack = QStackedWidget()
        self.monthly_view      = MonthlyView()
        self.budgeting_view    = BudgetingView()
        self.accounts_view     = AccountsView()
        self.transactions_view = TransactionsView()
        self.categories_view   = CategoriesView()

        for w in [
            self.monthly_view,
            self.budgeting_view,
            self.accounts_view,
            self.transactions_view,
            self.categories_view,
        ]:
            self.stack.addWidget(w)

        root.addLayout(nav, 0)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(container)

        self.monthly_btn.clicked.connect(self.open_monthly_view)
        self.budgeting_btn.clicked.connect(self.open_budgeting_view)
        self.accounts_btn.clicked.connect(self.open_accounts_view)
        self.import_btn.clicked.connect(self.open_import_wizard)
        self.transactions_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.transactions_view))
        self.categories_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.categories_view))

        self.open_monthly_view()

    def refresh_dependents(self):
        for view_name, method in [
            ("transactions_view", "load_transactions"),
            ("categories_view", "load_categories"),
            ("accounts_view", "refresh_data"),
            ("monthly_view", "load_months"),
            ("budgeting_view", "load_months"),
        ]:
            view = getattr(self, view_name, None)
            if view:
                fn = getattr(view, method, None)
                if fn:
                    fn()

    def open_import_wizard(self):
        dialog = ImportWizardDialog(self)
        if dialog.exec():
            self.refresh_dependents()
            self.monthly_view.refresh_data()
            self.budgeting_view.refresh_data()

    def open_accounts_view(self):
        self.accounts_view.refresh_data()
        self.stack.setCurrentWidget(self.accounts_view)

    def open_monthly_view(self):
        self.monthly_view.load_months()
        self.monthly_view.refresh_data()
        self.stack.setCurrentWidget(self.monthly_view)

    def open_budgeting_view(self):
        self.budgeting_view.load_months()
        self.budgeting_view.load_categories()
        self.budgeting_view.refresh_data()
        self.stack.setCurrentWidget(self.budgeting_view)
