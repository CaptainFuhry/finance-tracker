# finance_tracker/ui/account_filter_bar.py

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QButtonGroup,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from finance_tracker.data.db import SessionLocal
from finance_tracker.data.models import Account


class AccountFilterBar(QWidget):
    """
    Compact horizontal radio button bar for filtering by account.
    Auto-sizes to content — no fixed height, no scroll area.
    Emits account_changed(account_id). None = All Accounts.
    """

    account_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._account_id = None
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setup_ui()
        self.load_accounts()

    def setup_ui(self):
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 2, 0, 2)
        self._layout.setSpacing(16)

        self._label = QLabel("Account:")
        self._label.setStyleSheet("font-weight: bold;")
        self._layout.addWidget(self._label)

        self._button_group = QButtonGroup(self)
        self._button_group.buttonClicked.connect(self._on_selection_changed)

        self._layout.addStretch()

    def load_accounts(self):
        # Remove all existing radio buttons
        for btn in self._button_group.buttons():
            self._button_group.removeButton(btn)
            self._layout.removeWidget(btn)
            btn.deleteLater()

        # Remove the trailing stretch before re-adding buttons
        stretch_item = self._layout.itemAt(self._layout.count() - 1)
        if stretch_item and stretch_item.spacerItem():
            self._layout.removeItem(stretch_item)

        session = SessionLocal()
        try:
            accounts = session.query(Account).order_by(Account.account_name).all()
        finally:
            session.close()

        all_btn = QRadioButton("All Accounts")
        all_btn.setProperty("account_id", None)
        all_btn.setChecked(True)
        self._button_group.addButton(all_btn)
        self._layout.addWidget(all_btn)

        for account in accounts:
            btn = QRadioButton(account.account_name)
            btn.setProperty("account_id", account.account_id)
            self._button_group.addButton(btn)
            self._layout.addWidget(btn)

        self._layout.addStretch()
        self._account_id = None

    def _on_selection_changed(self, button):
        self._account_id = button.property("account_id")
        self.account_changed.emit(self._account_id)

    def current_account_id(self):
        return self._account_id

    def reset_to_all(self):
        buttons = self._button_group.buttons()
        if buttons:
            buttons[0].setChecked(True)
            self._account_id = None