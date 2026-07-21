import logging
import os
import webbrowser

from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QMainWindow, QMessageBox

from .. import __version__, __authors__, __organization__, __year__
from .dialogs.advanced_settings_handler import AdvancedSettingsHandler
from .managers.batch_coordinator import BatchCoordinator
from .managers.block_parser import BlockParser
from .managers.calibration_table_manager import CalibrationTableManager
from .managers.file_handlers import FileHandlers
from .managers.settings_manager import SettingsManager
from .managers.template_manager import TemplateManager
from .qtdesigner_files.gui_main import Ui_MainWindow
from .ui.ui_helpers import UIHelpers
from .ui.ui_setup import UISetup


def launch_xy_viewer(*args, **kwargs):
    """Lazily import and launch the XY spectrum viewer.

    Importing the underlying viewer module pulls in NumPy and the
    matplotlib Qt backend. To avoid slowing and potentially breaking
    application startup, defer that import until the viewer is actually
    requested.
    """
    from .viewers.xy_spectrum_viewer import launch_xy_viewer as _launch_xy_viewer
    return _launch_xy_viewer(*args, **kwargs)

class MainWindow(QMainWindow):
    """Main application window coordinating all GUI components. 
    
    This class acts as a thin coordinator, delegating business logic
    to specialized manager classes for settings, file handling,
    batch processing, etc.
    
    Attributes:
        logger: Application logger instance.
        ui: Main window UI object from Qt Designer.
        alignment_list_df: DataFrame containing alignment list data.
        analytes_list_df: DataFrame containing analytes list data.
        blocks: Dictionary of parsed block file data.
        advanced_settings_handler: Handler for advanced settings dialog.
        block_parser: Manager for block file parsing.
        calibration_table_manager: Manager for calibration table operations.
        file_handlers: Manager for file dialog operations.
        settings_manager: Manager for settings import/export.
        batch_coordinator: Manager for batch processing workflow.
    """

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setFixedSize(self.size())
        # Call UI setup methods.
        self.setup_ui()
        self.initialize_data_containers()
        self.initialize_dialogs()
        self.initialize_managers()
        self.initialize_default_blocks_directory()
        self.connect_signals()
    
    # --- UI setup methods ---

    def setup_ui(self) -> None:
        """Setup UI styling, icons, and tooltips."""
        UIHelpers.disable_spinbox_scroll(self)
        UISetup.setup_table_styling(self.ui.tableWidget_calibration)
        UISetup.setup_menu_icons(self.ui)
        UISetup.setup_button_icons(self.ui)
        UISetup.setup_tooltips(self.ui)
        self.setup_mode_indicator()
    
    def initialize_data_containers(self) -> None:
        """Initialize data container attributes."""
        self.alignment_list_df = None
        self.analytes_list_df = None
        self.analytes_ref_df = None
        self.blocks = None
        self.ms_only_mode = False  # Track whether in MS-only mode
    
    def initialize_dialogs(self) -> None:
        """Initialize all dialog instances."""
        self.advanced_settings_handler = AdvancedSettingsHandler(self)

    def initialize_managers(self) -> None:
        """Initialize all manager instances."""
        self.batch_coordinator = BatchCoordinator(
            self, self.ui, self.advanced_settings_handler.ui, self.logger
        )
        self.block_parser = BlockParser(self, self.ui)
        self.calibration_table_manager = CalibrationTableManager(self, self.ui)
        self.file_handlers = FileHandlers(self, self.ui)
        self.settings_manager = SettingsManager(
            self, self.ui, self.advanced_settings_handler.ui
        )
        self.template_manager = TemplateManager(self)
    
    def initialize_default_blocks_directory(self) -> None:
        """Set initial block files directory if it exists."""
        blocks_try = os.path.join(os.getcwd(), "blocks")
        if os.path.isdir(blocks_try):
            self.ui.path_blocks.addItem(blocks_try)
            self.block_parser.update_charge_carriers()
            self.block_parser.update_mass_modifiers()
    
    def setup_mode_indicator(self) -> None:
        """Create and add mode indicator label to the GUI."""
        from PyQt6.QtWidgets import QLabel
        from PyQt6.QtCore import Qt
        
        # Create mode indicator label
        self.mode_indicator_label = QLabel(self.ui.frame_calibration_quantitation)
        self.mode_indicator_label.setGeometry(380, 10, 100, 20)
        self.mode_indicator_label.setText("Mode: LC-MS")
        self.mode_indicator_label.setStyleSheet(
            "color: #00008B; font-weight: bold; font-size: 9pt;"
        )
        self.mode_indicator_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.mode_indicator_label.show()
    
    def set_ms_only_mode(self, enabled: bool) -> None:
        """Enable or disable MS-only mode in the GUI.
        
        Args:
            enabled: True to enable MS-only mode, False for LC-MS mode.
        """
        self.ms_only_mode = enabled

        # Keep the individual controls in sync with their container.  While a
        # disabled parent normally disables its children automatically, setting
        # these explicitly ensures that no alignment control can retain a
        # disabled state after returning from MS-only mode.
        alignment_controls = (
            self.ui.open_alignment_list,
            self.ui.pushButton_delete_alignment,
            self.ui.path_alignment_list,
            self.ui.alignment_time_window,
            self.ui.alignment_mz_window,
            self.ui.alignment_min_peaks,
            self.ui.alignment_sn_cutoff,
        )
        for control in alignment_controls:
            control.setEnabled(not enabled)
        
        if enabled:
            # MS-only mode: disable all LC-related features
            self.logger.info("Switching to MS-only mode")
            
            # Disable entire Alignment section with red text and hide spinbox values
            self.ui.frame_alignment.setEnabled(False)
            self.ui.frame_alignment.setStyleSheet(
                "QLabel { color: #a0a0a0; }"
                "QSpinBox, QDoubleSpinBox { color: transparent; }"
            )
            self.ui.alignment_time_window.setToolTip("")
            self.ui.alignment_mz_window.setToolTip("")
            self.ui.alignment_min_peaks.setToolTip("")
            self.ui.alignment_sn_cutoff.setToolTip("")
            
            # Disable sum spectrum resolution (LC-specific) and hide value
            self.ui.sum_spectrum_resolution.setEnabled(False)
            self.ui.sum_spectrum_resolution.setStyleSheet("color: transparent;")
            self.ui.sum_spectrum_resolution.setToolTip("")
            self.ui.label_resolution.setEnabled(False)
            self.ui.label_resolution.setStyleSheet("color: #a0a0a0;")
            
            # Hide calibration table (not applicable in MS-only mode)
            self.ui.tableWidget_calibration.setVisible(False)
            self.ui.pushButton_apply_sn.setVisible(False)
            self.ui.calibrant_sn_cutoff.setGeometry(
                self.ui.calibrant_sn_cutoff.x(),
                self.ui.calibrant_sn_cutoff.y(),
                221,
                self.ui.calibrant_sn_cutoff.height()
            )
            self.ui.label_calibrant_sn_cutoff.setText("Calibrant S/N cut-off")
            self.ui.calibrant_sn_cutoff.setToolTip(
                "Minimum signal-to-noise required for a calibrant to be used."
            )
            
            # Disable "Quantify aligned files only" checkbox
            self.ui.quantify_aligned.setEnabled(False)
            self.ui.quantify_aligned.setChecked(False)
            self.ui.quantify_aligned.setStyleSheet("color: #a0a0a0;")
            
            # Update mode indicator
            self.mode_indicator_label.setText("Mode: MS-only")
            self.mode_indicator_label.setStyleSheet(
                "color: #006400; font-weight: bold; font-size: 9pt;"
            )
        else:
            # LC-MS mode: enable all features
            self.logger.info("Switching to LC-MS mode")
            
            # Enable Alignment section and reset styling
            self.ui.frame_alignment.setEnabled(True)
            self.ui.frame_alignment.setStyleSheet("")
            self.ui.alignment_time_window.setToolTip(
                "Time window used around each alignment feature to determine its "
                "observed \nretention time. "
                "Can be overwritten for individual features in the alignment file."
            )
            self.ui.alignment_mz_window.setToolTip(
                "m/z window used around the exact m/z of an alignment feature\n"
                "when creating an extracted ion chromatogram. "
                "Can be overwritten\nfor individual features in the alignment file."
            )
            self.ui.alignment_min_peaks.setToolTip(
                "Minimum number of alignment features to use when aligning a\n"
                "chromatogram. When less features have a S/N above the cut-off,\n"
                "alignment fails for the corresponding sample."
            )
            self.ui.alignment_sn_cutoff.setToolTip(
                "Minimum signal-to-noise required for an alignment feature to be used.\n"
                "Can be overwritten for individual features in the alignment file."
            )
            
            # Enable sum spectrum resolution and reset styling
            self.ui.sum_spectrum_resolution.setEnabled(True)
            self.ui.sum_spectrum_resolution.setStyleSheet("")
            self.ui.sum_spectrum_resolution.setToolTip(
                "Number of data points per m/z unit in an LC-MS spectrum."
            )
            self.ui.label_resolution.setEnabled(True)
            self.ui.label_resolution.setStyleSheet("")
            
            # Show and enable calibration table
            self.ui.tableWidget_calibration.setVisible(True)
            self.ui.tableWidget_calibration.setEnabled(True)
            self.ui.tableWidget_calibration.setStyleSheet("")
            self.ui.pushButton_apply_sn.setVisible(True)
            self.ui.calibrant_sn_cutoff.setGeometry(
                self.ui.calibrant_sn_cutoff.x(),
                self.ui.calibrant_sn_cutoff.y(),
                73,
                self.ui.calibrant_sn_cutoff.height()
            )
            self.ui.label_calibrant_sn_cutoff.setText("Set all S/N cut-offs to:")
            self.ui.calibrant_sn_cutoff.setToolTip(
                "Minimum signal-to-noise required for a calibrant to be used.\n"
                "Can be modified per retention time window in the table below."
            )
            
            # Enable "Quantify aligned files only" checkbox and reset styling
            self.ui.quantify_aligned.setEnabled(True)
            self.ui.quantify_aligned.setStyleSheet("")
            
            # Update mode indicator
            self.mode_indicator_label.setText("Mode: LC-MS")
            self.mode_indicator_label.setStyleSheet(
                "color: #00008B; font-weight: bold; font-size: 9pt;"
            )

    def set_ref_file_mode(self, enabled: bool) -> None:
        """Disable or enable the quantitation m/z window and minimum isotopic
        fraction controls when a reference file is loaded.

        When a reference file is uploaded these values are already encoded in
        the file's `mz_window` column, so the corresponding GUI controls
        should be greyed out (same visual treatment as LC elements in
        MS-only mode).  Restoring them when a regular analytes list is
        loaded or the file is cleared.

        Args:
            enabled: True to enter ref-file mode (controls disabled),
                False to restore normal mode (controls enabled).
        """
        if enabled:
            self.ui.quantitation_mz_window.setEnabled(False)
            self.ui.quantitation_mz_window.setStyleSheet("color: transparent;")
            self.ui.quantitation_mz_window.setToolTip("")
            self.ui.label_quantitation_mz_window.setEnabled(False)
            self.ui.label_quantitation_mz_window.setStyleSheet("color: #a0a0a0;")
            self.ui.min_isotopic_fraction.setEnabled(False)
            self.ui.min_isotopic_fraction.setStyleSheet("color: transparent;")
            self.ui.min_isotopic_fraction.setToolTip("")
            self.ui.label_isotopic_fraction.setEnabled(False)
            self.ui.label_isotopic_fraction.setStyleSheet("color: #a0a0a0;")
        else:
            self.ui.quantitation_mz_window.setEnabled(True)
            self.ui.quantitation_mz_window.setStyleSheet("")
            self.ui.quantitation_mz_window.setToolTip(
                "m/z window used around the exact m/z of each isotopic peak"
                " for area integration\n"
                "(or for determining peak height, if enabled under advanced settings).\n"
                "Can be overwritten for individual analytes in the analytes list."
            )
            self.ui.label_quantitation_mz_window.setEnabled(True)
            self.ui.label_quantitation_mz_window.setStyleSheet("")
            self.ui.min_isotopic_fraction.setEnabled(True)
            self.ui.min_isotopic_fraction.setStyleSheet("")
            self.ui.min_isotopic_fraction.setToolTip(
                "Minimum fraction of the total isotopic pattern that should\n"
                "be integrated per analyte and charge state."
            )
            self.ui.label_isotopic_fraction.setEnabled(True)
            self.ui.label_isotopic_fraction.setStyleSheet("")

    def connect_signals(self) -> None:
        """Connect all UI signals to their handlers."""
        # File operation buttons.
        self.ui.open_blocks_folder.clicked.connect(
            self.file_handlers.open_blocks_folder
        )
        self.ui.open_alignment_list.clicked.connect(
            self.file_handlers.open_alignment_list
        )
        self.ui.open_analytes_list.clicked.connect(
            self.file_handlers.open_analytes_list
        )
        self.ui.open_mzxml_path.clicked.connect(
            self.file_handlers.open_mzxml_path
        )
        self.ui.pushButton_start_processing.clicked.connect(
            self.batch_coordinator.start_batch_process
        )
        self.ui.pushButton_apply_sn.clicked.connect(
            self.calibration_table_manager.apply_sn_cutoff
        )
        self.ui.pushButton_delete_alignment.clicked.connect(
            self.file_handlers.clear_alignment_file
        )
        self.ui.pushButton_delete_analytes.clicked.connect(
            self.file_handlers.clear_analytes_file
        )
        # Toolbar actions.
        self.ui.actionAbout.triggered.connect(
            self.open_about
        )
        self.ui.actionAdvanced_settings.triggered.connect(
            self.open_advanced_settings
        )
        self.ui.actionDocumentation.triggered.connect(
            self.open_documentation
        )
        self.ui.actionExit.triggered.connect(
            self.close
        )
        self.ui.actionExport_settings.triggered.connect(
            self.settings_manager.export_settings
        )
        self.ui.actionImport_settings.triggered.connect(
            self.settings_manager.import_settings
        )
        self.ui.actionRevert_to_default_settings.triggered.connect(
            self.settings_manager.reset_settings
        )
        self.ui.actionReport_a_bug.triggered.connect(
            self.report_a_bug
        )
        self.ui.actionAlignment_list.triggered.connect(
            self.download_alignment_template
        )
        self.ui.actionAnalytes_list.triggered.connect(
            self.download_analytes_template
        )
        self.ui.actionBlock_file.triggered.connect(
            self.download_block_template
        )
        self.ui.actionVisualize_mass_spectrum.triggered.connect(
            lambda: launch_xy_viewer(self)
        )

    # --- Functions connected to signals ---

    def open_about(self) -> None:
        """Show popup box with information about the software, including a clickable URL."""
        authors_str = ", ".join(__authors__)
        about_text = (
            "Released under the MIT License.<br><br>"
            f"Copyright © {__year__} {authors_str}<br>"
            f"<i>{__organization__}</i><br><br>"
            "Based on <a href='https://github.com/Tarskin/LaCyTools'>LaCyTools</a>"
            " and <a href='https://github.com/Tarskin/MassyTools'>MassyTools</a>"
            ", both created by Bas Jansen and released under the Apache License, Version 2.0.<br><br>"
            "<a href='https://github.com/stainawarijar/SweetSuite'>SweetSuite on GitHub</a>"
        )
        UIHelpers.show_message_box(
            self,
            title="About",
            text=f"SweetSuite version {__version__}",
            informative_text=about_text,
            icon="Information"
        )

    def open_advanced_settings(self) -> None:
        """Open advanced settings dialog."""
        self.advanced_settings_handler.show_dialog()

    def open_documentation(self) -> None:
        """Direct to SweetSuite README page on GitHub."""
        webbrowser.open("https://github.com/stainawarijar/SweetSuite/blob/main/README.md")
    
    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close event (e.g., clicking the X button)."""
        # Set up confirmation box.
        box = QMessageBox(self)
        box.setWindowTitle("Exit program")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("Do you want to exit SweetSuite?")
        yes_button = box.addButton("Yes, exit", QMessageBox.ButtonRole.YesRole)
        yes_button.setStyleSheet(
            "background-color: #8B0000; color: white; font-weight: bold;"
        )
        cancel_button = box.addButton("Cancel", QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(cancel_button)
        box.exec()
        # Check confirmation.
        if box.clickedButton() == yes_button:
            event.accept()
        else:
            event.ignore()
    
    def download_alignment_template(self) -> None:
        """Download alignment template Excel file."""
        self.template_manager.download_template("alignment")

    def download_analytes_template(self) -> None:
        """Download analytes template Excel file."""
        self.template_manager.download_template("analytes")

    def download_block_template(self) -> None:
        """Download block file template."""
        self.template_manager.download_template("block")
    
    def report_a_bug(self) -> None:
        """Direct to SweetSuite issues page on GitHub."""
        webbrowser.open("https://github.com/stainawarijar/SweetSuite/issues")
