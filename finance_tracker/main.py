import sys
from PySide6.QtWidgets import QApplication
from finance_tracker.ui.main_window import MainWindow
from config import APP_NAME

def run():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

