from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton
from finance_tracker.ui.accounts_view import AccountsView


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Finance Tracker")
        self.resize(1200, 800)

        container = QWidget()
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)

        title = QLabel("Finance Tracker")
        subtitle = QLabel("Phase 1: Foundation Window")
        refresh_button = QPushButton("Refresh Analytics")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(refresh_button)

        self.accounts_view = AccountsView()
        layout.addWidget(self.accounts_view)