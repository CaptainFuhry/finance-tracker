from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
)

from finance_tracker.ui.accounts_view import AccountsView
from finance_tracker.ui.categories_view import CategoriesView
from finance_tracker.ui.transactions_view import TransactionsView
from finance_tracker.ui.running_balance_view import RunningBalanceView
from finance_tracker.ui.import_wizard import ImportWizardDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Finance Tracker")
        self.resize(1400, 900)

        container = QWidget()
        root = QHBoxLayout(container)

        nav = QVBoxLayout()
        self.accounts_btn = QPushButton("Accounts")
        self.transactions_btn = QPushButton("Transactions")
        self.categories_btn = QPushButton("Categories")
        self.running_balance_btn = QPushButton("Running Balance")
        self.import_btn = QPushButton("Import Transactions")

        nav.addWidget(self.accounts_btn)
        nav.addWidget(self.transactions_btn)
        nav.addWidget(self.categories_btn)
        nav.addWidget(self.running_balance_btn)
        nav.addWidget(self.import_btn)
        nav.addStretch()

        self.stack = QStackedWidget()
        self.accounts_view = AccountsView()
        self.transactions_view = TransactionsView()
        self.categories_view = CategoriesView()
        self.running_balance_view = RunningBalanceView()

        self.stack.addWidget(self.accounts_view)
        self.stack.addWidget(self.transactions_view)
        self.stack.addWidget(self.categories_view)
        self.stack.addWidget(self.running_balance_view)

        root.addLayout(nav, 0)
        root.addWidget(self.stack, 1)

        self.setCentralWidget(container)

        self.accounts_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.accounts_view))
        self.transactions_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.transactions_view))
        self.categories_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.categories_view))
        self.running_balance_btn.clicked.connect(self.open_running_balance)
        self.import_btn.clicked.connect(self.open_import_wizard)

    def open_import_wizard(self):
        dialog = ImportWizardDialog(self)
        if dialog.exec():
            if hasattr(self.transactions_view, "load_transactions"):
                self.transactions_view.load_transactions()
            if hasattr(self.categories_view, "load_categories"):
                self.categories_view.load_categories()
            if hasattr(self.running_balance_view, "load_accounts"):
                self.running_balance_view.load_accounts()
            if hasattr(self.running_balance_view, "refresh_data"):
                self.running_balance_view.refresh_data()

    def open_running_balance(self):
        if hasattr(self.running_balance_view, "load_accounts"):
            self.running_balance_view.load_accounts()
        if hasattr(self.running_balance_view, "refresh_data"):
            self.running_balance_view.refresh_data()
        self.stack.setCurrentWidget(self.running_balance_view)