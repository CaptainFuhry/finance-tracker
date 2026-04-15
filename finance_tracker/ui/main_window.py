from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton, QTabWidget, QHBoxLayout
from finance_tracker.ui.accounts_view import AccountsView
from finance_tracker.ui.transactions_view import TransactionsView
from finance_tracker.ui.categories_view import CategoriesView
from finance_tracker.ui.import_wizard import ImportWizardDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Finance Tracker")
        self.resize(1200, 800)

        container = QWidget()
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)

        # Header row
        header_layout = QHBoxLayout()
        title = QLabel("Finance Tracker")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.import_button = QPushButton("Import Transactions")
        self.refresh_button = QPushButton("Refresh")
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.import_button)
        header_layout.addWidget(self.refresh_button)
        layout.addLayout(header_layout)

        # Tabs
        self.tabs = QTabWidget()
        self.accounts_view = AccountsView()
        self.transactions_view = TransactionsView()
        self.categories_view = CategoriesView()

        self.tabs.addTab(self.accounts_view, "Accounts")
        self.tabs.addTab(self.transactions_view, "Transactions")
        self.tabs.addTab(self.categories_view, "Categories")
        self.tabs.setCurrentIndex(0)

        layout.addWidget(self.tabs)

        self.import_button.clicked.connect(self.open_import_wizard)
        self.refresh_button.clicked.connect(self.refresh_active_tab)

    def open_import_wizard(self):
        dialog = ImportWizardDialog(self)
        if dialog.exec() == ImportWizardDialog.Accepted:
            self.transactions_view.load_transactions()
            self.categories_view.load_categories()

    def refresh_active_tab(self):
        index = self.tabs.currentIndex()
        if index == 0:
            self.accounts_view.load_accounts()
        elif index == 1:
            self.transactions_view.load_transactions()
        elif index == 2:
            self.categories_view.load_categories()