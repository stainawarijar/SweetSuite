"""LC-FLD settings page designed in gui_lc_fld.ui."""

import os

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFileDialog, QWidget

from ..utils import utils
from .qtdesigner_files.gui_lc_fld import Ui_Form


class FldPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.setup_ui()

    def setup_ui(self) -> None:
        """Apply presentation details owned by the LC-FLD page."""
        self.setup_button_icons()
        self.setup_tooltips()

    def setup_button_icons(self) -> None:
        """Configure icons for controls on this page."""
        icon_path = utils.resource_path(os.path.join(
            "sweet_suite", "gui", "assets", "google-material-icons"
        ))

        self.ui.open_peaks_list.setIcon(QIcon(os.path.join(
            icon_path, "file_open.svg"
        )))
        self.ui.open_alignment_list.setIcon(QIcon(os.path.join(
            icon_path, "file_open.svg"
        )))
        self.ui.open_mzxml_path.setIcon(QIcon(os.path.join(
            icon_path, "folder_open.svg"
        )))
        self.ui.pushButton_delete_peaks.setIcon(QIcon(os.path.join(
            icon_path, "trash.svg"
        )))
        self.ui.pushButton_delete_alignment.setIcon(QIcon(os.path.join(
            icon_path, "trash.svg"
        )))

    def setup_tooltips(self) -> None:
        """Configure tooltips for controls on this page."""
        self.ui.open_peaks_list.setToolTip("Browse")
        self.ui.open_alignment_list.setToolTip("Browse")
        self.ui.open_mzxml_path.setToolTip("Browse")
        self.ui.pushButton_delete_peaks.setToolTip("Clear list")
        self.ui.pushButton_delete_alignment.setToolTip("Clear list")
        self.ui.alignment_time_window.setToolTip(
            "LC-FLD alignment time-window tooltip placeholder."
        )
        self.ui.alignment_min_peaks.setToolTip(
            "LC-FLD minimum-peaks tooltip placeholder."
        )
        self.ui.alignment_sn_cutoff.setToolTip(
            "LC-FLD S/N cut-off tooltip placeholder."
        )
        self.ui.quantify_aligned.setToolTip(
            "LC-FLD aligned-files option tooltip placeholder."
        )

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
