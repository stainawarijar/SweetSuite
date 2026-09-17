"""Persistent MS settings page, designed in gui_ms.ui"""

from PyQt6.QtWidgets import QWidget

from .qtdesigner_files.gui_ms import Ui_Form


class MsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
