"""Persistent MS settings page, designed in gui_ms.ui."""

import os

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QHeaderView, QWidget

from ..utils import utils
from .qtdesigner_files.gui_ms import Ui_Form


class MsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.setup_ui()

    def setup_ui(self) -> None:
        """Apply presentation details owned by the MS page."""
        self.setup_button_icons()
        self.setup_tooltips()
        self.setup_calibration_table()

    def setup_button_icons(self) -> None:
        """Configure icons for controls on this page."""
        icon_path = utils.resource_path(os.path.join(
            "sweet_suite", "gui", "assets", "google-material-icons"
        ))

        self.ui.pushButton_apply_sn.setIcon(QIcon(os.path.join(
            icon_path, "apply_sn_cutoff.svg"
        )))
        self.ui.pushButton_apply_sn.setIconSize(QSize(18, 18))
        self.ui.pushButton_apply_sn.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft
        )
        self.ui.pushButton_apply_sn.setText("Apply to all rows\t\t")

        self.ui.open_analytes_list.setIcon(QIcon(os.path.join(
            icon_path, "file_open.svg"
        )))
        self.ui.open_alignment_list.setIcon(QIcon(os.path.join(
            icon_path, "file_open.svg"
        )))
        self.ui.open_blocks_folder.setIcon(QIcon(os.path.join(
            icon_path, "folder_open.svg"
        )))
        self.ui.open_mzxml_path.setIcon(QIcon(os.path.join(
            icon_path, "folder_open.svg"
        )))

        self.ui.pushButton_delete_alignment.setIcon(QIcon(os.path.join(
            icon_path, "trash.svg"
        )))
        self.ui.pushButton_delete_analytes.setIcon(QIcon(os.path.join(
            icon_path, "trash.svg"
        )))

    def setup_tooltips(self) -> None:
        """Configure tooltips for controls on this page."""
        self.ui.pushButton_apply_sn.setToolTip(
            "Apply to all retention time windows"
        )
        self.ui.open_alignment_list.setToolTip("Browse")
        self.ui.open_analytes_list.setToolTip("Browse")
        self.ui.open_blocks_folder.setToolTip("Browse")
        self.ui.open_mzxml_path.setToolTip("Browse")
        self.ui.pushButton_delete_alignment.setToolTip("Clear list")
        self.ui.pushButton_delete_analytes.setToolTip("Clear list")

        self.ui.sum_spectrum_resolution.setToolTip(
            "Number of data points per m/z unit (Th) in an LC-MS spectrum."
        )
        self.ui.background_mass_window.setToolTip(
            "Determines the m/z window used around each analyte to determine "
            "the background signal.\nThe background m/z window equals the mass "
            "window (Da) divided by the analyte charge state."
        )
        self.ui.calibration_mass_window.setToolTip(
            "Determines the m/z window used around the exact m/z of a calibrant "
            "peak to determine its observed m/z.\nThe calibration m/z window "
            "equals the mass window (Da) divided by the calibrant charge state."
        )
        self.ui.quantitation_mz_window.setToolTip(
            "m/z window used around the exact m/z of each isotopic peak"
            " for area quantitation\n"
            "(or for determining peak height, if enabled under advanced "
            "settings).\n"
            "Can be overwritten for individual analytes in the analytes list."
        )
        self.ui.min_isotopic_fraction.setToolTip(
            "Minimum fraction of the total isotopic pattern that should\n"
            "be quantified per analyte and charge state."
        )
        self.ui.min_calibrant_number.setToolTip(
            "Minimum number of calibrants to use when calibrating a sum "
            "spectrum.\nWhen less calibrants have a S/N above the cut-off, "
            "calibration fails."
        )
        self.ui.calibrant_sn_cutoff.setToolTip(
            "Minimum signal-to-noise required for a calibrant to be used.\n"
            "Can be modified per retention time window in the table below."
        )
        self.ui.alignment_time_window.setToolTip(
            "Time window used around each alignment feature to determine its "
            "observed \nretention time. Can be overwritten for individual "
            "features in the alignment file."
        )
        self.ui.alignment_mz_window.setToolTip(
            "m/z window used around the exact m/z of an alignment feature\n"
            "when creating an extracted ion chromatogram. Can be overwritten\n"
            "for individual features in the alignment file."
        )
        self.ui.alignment_min_peaks.setToolTip(
            "Minimum number of alignment features to use when aligning a\n"
            "chromatogram. When less features have a S/N above the cut-off,\n"
            "alignment fails for the corresponding measurement."
        )
        self.ui.alignment_sn_cutoff.setToolTip(
            "Minimum signal-to-noise required for an alignment feature to be "
            "used.\nCan be overwritten for individual features in the "
            "alignment file."
        )

    def setup_calibration_table(self) -> None:
        """Configure the calibration table header."""
        header = self.ui.tableWidget_calibration.horizontalHeader()
        header.setStyleSheet("""
            QHeaderView::section {
                color: black;
                background-color: #f0f0f0;
                font-weight: bold;
                font-size: 10pt;
                padding: 3px;
            }
        """)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
