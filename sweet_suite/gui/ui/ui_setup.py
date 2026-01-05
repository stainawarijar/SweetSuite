import os
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QHeaderView

from ...utils import utils


class UISetup:
    """Handles UI setup operations."""
    
    @staticmethod
    def get_icon_path() -> str:
        """Get the path to the icons directory."""
        return utils.resource_path(os.path.join(
            "sweet_suite", "gui", "assets", "google-material-icons"
        ))
    
    @staticmethod
    def setup_menu_icons(ui) -> None:
        """Configure all menu action icons.
        
        Args:
            ui: The main window UI object.
        """
        icon_path = UISetup.get_icon_path()
        
        # File menu
        ui.actionImport_settings.setIcon(QIcon(os.path.join(
            icon_path, "actionImport_settings.svg"
        )))
        ui.actionExport_settings.setIcon(QIcon(os.path.join(
            icon_path, "actionExport_settings.svg"
        )))
        ui.actionRevert_to_default_settings.setIcon(QIcon(os.path.join(
            icon_path, "reset_settings.svg"
        )))
        ui.actionExit.setIcon(QIcon(os.path.join(
            icon_path, "actionExit.svg"
        )))
        
        # Templates menu
        ui.menuTemplates.setIcon(QIcon(os.path.join(
            icon_path, "sheet.svg"
        )))
        ui.actionAlignment_list.setIcon(QIcon(os.path.join(
            icon_path, "download.svg"
        )))
        ui.actionAnalytes_list.setIcon(QIcon(os.path.join(
            icon_path, "download.svg"
        )))
        ui.actionBlock_file.setIcon(QIcon(os.path.join(
            icon_path, "download.svg"
        )))
        
        # Tools menu
        ui.actionAdvanced_settings.setIcon(QIcon(os.path.join(
            icon_path, "actionAdvanced_settings.svg"
        )))
        
        # Help menu
        ui.actionDocumentation.setIcon(QIcon(os.path.join(
            icon_path, "actionDocumentation.svg"
        )))
        ui.actionReport_a_bug.setIcon(QIcon(os.path.join(
            icon_path, "actionReport_a_bug.svg"
        )))
        ui.actionAbout.setIcon(QIcon(os.path.join(
            icon_path, "actionAbout.svg"
        )))
    
    @staticmethod
    def setup_button_icons(ui) -> None:
        """Configure button icons.
        
        Args:
            ui: The main window UI object
        """
        icon_path = UISetup.get_icon_path()
        
        # Apply S/N cut-off button
        ui.pushButton_apply_sn.setIcon(QIcon(os.path.join(
            icon_path, "apply_sn_cutoff.svg"
        )))
        ui.pushButton_apply_sn.setIconSize(QSize(18, 18))
        
        # Open file buttons
        ui.open_analytes_list.setIcon(QIcon(os.path.join(
            icon_path, "file_open.svg"
        )))
        ui.open_alignment_list.setIcon(QIcon(os.path.join(
            icon_path, "file_open.svg"
        )))
        ui.open_blocks_folder.setIcon(QIcon(os.path.join(
            icon_path, "folder_open.svg"
        )))
        ui.open_mzxml_path.setIcon(QIcon(os.path.join(
            icon_path, "folder_open.svg"
        )))
        
        # Clear buttons
        ui.pushButton_delete_alignment.setIcon(QIcon(os.path.join(
            icon_path, "trash.svg"
        )))
        ui.pushButton_delete_analytes.setIcon(QIcon(os.path.join(
            icon_path, "trash.svg"
        )))
    
    @staticmethod
    def setup_tooltips(ui) -> None:
        """Configure tooltips for all widgets.
        
        Args:
            ui: The main window UI object
        """
        # Button tooltips
        ui.pushButton_apply_sn.setToolTip("Apply to all retention time windows")
        ui.open_alignment_list.setToolTip("Browse")
        ui.open_analytes_list.setToolTip("Browse")
        ui.open_blocks_folder.setToolTip("Browse")
        ui.open_mzxml_path.setToolTip("Browse")
        ui.pushButton_delete_alignment.setToolTip("Clear list")
        ui.pushButton_delete_analytes.setToolTip("Clear list")
        
        # Settings tooltips
        ui.sum_spectrum_resolution.setToolTip(
            "Number of data points per m/z unit."
        )
        ui.background_mass_window.setToolTip(
            "m/z window used around each analyte to determine " \
            "the background signal."
        )
        ui.calibration_mass_window.setToolTip(
            "Mass window used around the exact m/z of a calibrant" \
            " to determine its observed m/z."
        )
        ui.quantitation_mz_window.setToolTip(
            "m/z window used around the exact m/z of each isotopic peak" \
            " for area integration.\n" \
            "Can be overwritten for individual analytes in the analytes list."
        )
        ui.min_isotopic_fraction.setToolTip(
            "Minimum fraction of the total isotopic pattern that should\n" \
            "be integrated per analyte and charge state."
        )
        ui.min_calibrant_number.setToolTip(
            "Minimum number of calibrants to use when calibrating a sum spectrum.\n" \
            "When less calibrants have a S/N above the cut-off, calibration fails."
        )
        ui.calibrant_sn_cutoff.setToolTip(
            "Minimum signal-to-noise required for a calibrant to be used.\n"
            "Can be modified per retention time window in the table below."
        )
        ui.alignment_time_window.setToolTip(
            "Time window used around each alignment feature to determine its "\
            "observed \nretention time. "
            "Can be overwritten for individual features in the alignment file."
        )
        ui.alignment_mz_window.setToolTip(
            "m/z window used around the exact m/z of an alignment feature\n" \
            "when creating an extracted ion chromatogram. "
            "Can be overwritten\nfor individual features in the alignment file."
        )
        ui.alignment_min_peaks.setToolTip(
            "Minimum number of alignment features to use when aligning a\n" \
            "chromatogram. When less features have a S/N above the cut-off,\n" \
            "alignment fails for the corresponding sample."
        )
        ui.alignment_sn_cutoff.setToolTip(
            "Minimum signal-to-noise required for an alignment feature to be used.\n"
            "Can be overwritten for individual features in the alignment file."
        )
    
    @staticmethod
    def setup_table_styling(table_widget) -> None:
        """Configure calibration table header styling.
        
        Args:
            table_widget: The table widget to style
        """
        header = table_widget.horizontalHeader()
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
