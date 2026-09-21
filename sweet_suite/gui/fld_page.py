"""LC-FLD settings page designed in gui_lc_fld.ui."""

from PyQt6.QtWidgets import QFileDialog, QWidget

from .qtdesigner_files.gui_lc_fld import Ui_Form


class FldPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.ui.open_mzxml_path.clicked.connect(self.select_raw_folder)
        self.ui.open_peaks_list.clicked.connect(
            lambda: self.select_list(self.ui.path_peaks_list, "Select LC-FLD peaks list")
        )
        self.ui.open_alignment_list.clicked.connect(
            lambda: self.select_list(self.ui.path_alignment_list, "Select LC-FLD alignment list")
        )
        self.ui.pushButton_delete_peaks.clicked.connect(self.ui.path_peaks_list.clear)
        self.ui.pushButton_delete_alignment.clicked.connect(self.ui.path_alignment_list.clear)

    def select_raw_folder(self) -> None:
        """Select the raw-data directory independently of the MS page."""
        path = QFileDialog.getExistingDirectory(self, "Select LC-FLD raw data folder")
        if path:
            self.ui.path_mzxml.clear()
            self.ui.path_mzxml.addItem(path)

    def select_list(self, widget, title: str) -> None:
        """Select an Excel input list; parsing belongs to the FLD pipeline."""
        path, _ = QFileDialog.getOpenFileName(self, title, "", "Excel files (*.xlsx)")
        if path:
            widget.clear()
            widget.addItem(path)
