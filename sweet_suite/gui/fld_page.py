"""LC-FLD settings page designed in gui_lc-fld.ui."""

from importlib import import_module

from PyQt6.QtWidgets import QWidget


# Designer's generated filename contains a hyphen, so load it by module name.
Ui_Form = import_module(".qtdesigner_files.gui_lc-fld", __package__).Ui_Form


class FldPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
