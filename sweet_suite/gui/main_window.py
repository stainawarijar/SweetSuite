import logging
import os
import webbrowser

from PyQt6.QtCore import QSignalBlocker, Qt
from PyQt6.QtGui import QCloseEvent, QIcon
from PyQt6.QtWidgets import QFrame, QLabel, QMainWindow, QMessageBox, QVBoxLayout

from .. import __version__, __authors__, __organization__, __year__
from ..utils import utils
from .dialogs.advanced_settings_handler import AdvancedSettingsHandler
from .managers.batch_coordinator import BatchCoordinator
from .managers.block_parser import BlockParser
from .managers.calibration_table_manager import CalibrationTableManager
from .managers.file_handlers import FileHandlers
from .managers.settings_manager import SettingsManager
from .managers.template_manager import TemplateManager
from .ms_page import MsPage
from .fld_page import FldPage
from .processing_mode import ProcessingMode
from .qtdesigner_files.gui_main import Ui_MainWindow
from .ui.ui_helpers import UIHelpers


def launch_xy_viewer(*args, **kwargs):
    """Lazily import and launch the XY spectrum viewer.

    Importing the underlying viewer module pulls in NumPy, Plotly Express, and
    Qt WebEngine. To avoid slowing and potentially breaking
    application startup, defer that import until the viewer is actually
    requested.
    """
    from .viewers.xy_spectrum_viewer import launch_xy_viewer as _launch_xy_viewer
    return _launch_xy_viewer(*args, **kwargs)

def launch_chromatogram_viewer(parent=None):
    """Load Plotly and WebEngine only when the chromatogram tool is opened."""
    from .viewers.chromatogram_viewer import launch_chromatogram_viewer as launch
    return launch(parent)


class MainWindow(QMainWindow):
    """Main application window coordinating all GUI components. 
    
    This class acts as a thin coordinator, delegating business logic
    to specialized manager classes for settings, file handling,
    batch processing, etc.
    
    Attributes:
        logger: Application logger instance.
        ui: Main window shell UI object from Qt Designer.
        ms_page: Persistent settings page shared by LC-MS and MS-only modes.
        ms_ui: MS page UI object retained by the existing managers.
        processing_mode: Selected or input-file-detected processing mode.
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
        launch_size = self.size()
        self.ms_page = MsPage(self.ui.page)
        self.ms_ui = self.ms_page.ui
        page_layout = QVBoxLayout(self.ui.page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(self.ms_page)
        self.fld_page = self.ui.page_2
        self.fld_form = FldPage(self.fld_page)
        self.fld_ui = self.fld_form.ui
        fld_layout = QVBoxLayout(self.fld_page)
        fld_layout.setContentsMargins(0, 0, 0, 0)
        fld_layout.addWidget(self.fld_form)
        self.setFixedSize(launch_size)
        # CustomizeWindowHint makes the title-bar controls explicit rather
        # than allowing the platform to supply the default window buttons.
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        # setFixedSize already prevents resizing. The Windows dialog-border
        # hint interferes with per-monitor DPI changes.
        self.setWindowIcon(QIcon(utils.resource_path(os.path.join(
            "sweet_suite", "resources", "images", "logo_head.png"
        ))))
        # Call UI setup methods.
        self.initialize_data_containers()
        self.setup_ui()
        self.initialize_dialogs()
        self.initialize_managers()
        self.initialize_default_blocks_directory()
        self.connect_signals()
        self.set_processing_mode(ProcessingMode.LC_MS)
        # Keep the initial size from the Designer form after initialization.
        self.resize(launch_size)
    
    # --- UI setup methods ---

    def setup_ui(self) -> None:
        """Setup UI styling, icons, and tooltips."""
        UIHelpers.disable_spinbox_scroll(self)
        self.setup_menu_icons()
        self.setup_quadratic_window_indicator()

    def setup_menu_icons(self) -> None:
        """Configure icons for actions owned by the main-window shell."""
        icon_path = utils.resource_path(os.path.join(
            "sweet_suite", "gui", "assets", "google-material-icons"
        ))

        action_icons = {
            self.ui.actionImport_settings: "actionImport_settings.svg",
            self.ui.actionExport_settings: "actionExport_settings.svg",
            self.ui.actionRevert_to_default_settings: "reset_settings.svg",
            self.ui.actionExit: "actionExit.svg",
            self.ui.actionAlignment_list: "download.svg",
            self.ui.actionAnalytes_list: "download.svg",
            self.ui.actionBlock_file: "download.svg",
            self.ui.actionLC_FLD_alignment_list: "download.svg",
            self.ui.actionLC_FLD_peaks_list: "download.svg",
            self.ui.actionAdvanced_settings: "actionAdvanced_settings.svg",
            self.ui.actionVisualize_mass_spectrum:
                "actionVisualize_mass_spectrum.svg",
            self.ui.actionView_LC_FLD_chromatogram:
                "actionView_LC_FLD_chromatogram.svg",
            self.ui.actionDocumentation: "actionDocumentation.svg",
            self.ui.actionReport_a_bug: "actionReport_a_bug.svg",
            self.ui.actionAbout: "actionAbout.svg",
        }
        for action, filename in action_icons.items():
            action.setIcon(QIcon(os.path.join(icon_path, filename)))

        self.ui.menuTemplates.setIcon(QIcon(os.path.join(
            icon_path, "sheet.svg"
        )))
    
    def initialize_data_containers(self) -> None:
        """Initialize data container attributes."""
        self.alignment_list_df = None
        self.analytes_list_df = None
        self.analytes_ref_df = None
        self.blocks = None
        self.ms_only_mode = False  # Track whether in MS-only mode
        self.ref_file_mode = False
        self.processing_mode = ProcessingMode.LC_MS
    
    def initialize_dialogs(self) -> None:
        """Initialize all dialog instances."""
        self.advanced_settings_handler = AdvancedSettingsHandler(self)

    def initialize_managers(self) -> None:
        """Initialize all manager instances."""
        self.batch_coordinator = BatchCoordinator(
            self, self.ms_ui, self.advanced_settings_handler.ui, self.logger
        )
        self.block_parser = BlockParser(self, self.ms_ui)
        self.calibration_table_manager = CalibrationTableManager(self, self.ms_ui)
        self.file_handlers = FileHandlers(self, self.ms_ui)
        self.settings_manager = SettingsManager(
            self, self.ms_ui, self.advanced_settings_handler.ui
        )
        self.template_manager = TemplateManager(self)
    
    def initialize_default_blocks_directory(self) -> None:
        """Set initial block files directory if it exists."""
        blocks_try = os.path.join(os.getcwd(), "blocks")
        if os.path.isdir(blocks_try):
            self.ms_ui.path_blocks.addItem(blocks_try)
            self.block_parser.update_charge_carriers()
            self.block_parser.update_mass_modifiers()
    
    def setup_quadratic_window_indicator(self) -> None:
        """Create the disabled message shown in place of the fixed window."""
        spinbox = self.ms_ui.quantitation_mz_window
        self.quadratic_window_mode = False
        self.quadratic_window_indicator = QLabel(
            "Quadratic window enabled",
            self.ms_ui.frame_calibration_quantitation,
        )
        geo = spinbox.geometry()
        self.quadratic_window_indicator.setGeometry(
            geo.x(), geo.y() + 1, geo.width(), geo.height() - 1
        )
        self.quadratic_window_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.quadratic_window_indicator.setFrameShape(QFrame.Shape.StyledPanel)
        self.quadratic_window_indicator.setStyleSheet(
            "QLabel:disabled { color: #555555; }"
        )
        self.quadratic_window_indicator.setToolTip(
            self.ms_ui.quantitation_mz_window.toolTip()
        )
        self.quadratic_window_indicator.setEnabled(False)
        self.quadratic_window_indicator.hide()

    def set_quadratic_window_mode(self, enabled: bool) -> None:
        """Replace the fixed quantitation window with a quadratic-mode notice."""
        self.quadratic_window_mode = enabled
        self.quadratic_window_indicator.setVisible(enabled)
        self.ms_ui.quantitation_mz_window.setVisible(not enabled)
        self.update_quantitation_window_state()

    def update_quantitation_window_state(self) -> None:
        """Apply the combined quadratic- and reference-file disabled state."""
        quadratic = self.quadratic_window_mode
        disabled = quadratic or self.ref_file_mode
        self.ms_ui.quantitation_mz_window.setEnabled(not disabled)
        # Quadratic mode replaces only the input box; its title remains active
        # and black. Reference-file mode retains its existing greyed title.
        label_disabled = self.ref_file_mode and not quadratic
        self.ms_ui.label_quantitation_mz_window.setEnabled(not label_disabled)
        self.ms_ui.label_quantitation_mz_window.setStyleSheet(
            "color: #a0a0a0;" if label_disabled else ""
        )

        if self.ref_file_mode and not quadratic:
            self.ms_ui.quantitation_mz_window.setStyleSheet("color: transparent;")
            self.ms_ui.quantitation_mz_window.setToolTip("")
        elif not quadratic:
            self.ms_ui.quantitation_mz_window.setStyleSheet("")
            self.ms_ui.quantitation_mz_window.setToolTip(
                "m/z window used around the exact m/z of each isotopic peak"
                " for area quantitation\n"
                "(or for determining peak height, if enabled under advanced settings).\n"
                "Can be overwritten for individual analytes in the analytes list."
            )
    
    def set_processing_mode(self, mode: ProcessingMode) -> None:
        """Switch pages unless an uploaded analyte/reference file fixes the mode."""
        if self.analytes_list_df is not None or self.analytes_ref_df is not None:
            self.sync_mode_selection()
            return
        if mode == ProcessingMode.LC_FLD:
            self.processing_mode = mode
            self.sync_mode_selection()
            self.logger.info("Using LC-FLD mode")
        else:
            self.set_ms_only_mode(mode == ProcessingMode.MS_ONLY)

    def sync_mode_selection(self) -> None:
        """Synchronize the selector, page, lock, and menu actions."""
        selector = self.ui.comboBox_processing_mode
        with QSignalBlocker(selector):
            selector.setCurrentText(self.processing_mode.value)
        locked = self.analytes_list_df is not None or self.analytes_ref_df is not None
        selector.setEnabled(not locked)
        selector.setToolTip(
            "Clear the uploaded analytes list or reference file to change mode."
            if locked else "Select a processing mode."
        )
        ms_mode = self.processing_mode != ProcessingMode.LC_FLD
        self.ui.stackedWidget.setCurrentWidget(
            self.ui.page if ms_mode else self.fld_page
        )
        # Toolbar and menu actions stay available in every processing mode.
        # Some actions open MS-specific tools, but selecting LC-FLD should not
        # prevent users from accessing them.
        for action in (
            self.ui.actionImport_settings,
            self.ui.actionExport_settings,
            self.ui.actionRevert_to_default_settings,
            self.ui.actionAdvanced_settings,
            self.ui.actionVisualize_mass_spectrum,
            self.ui.actionAlignment_list,
            self.ui.actionAnalytes_list,
            self.ui.actionBlock_file,
        ):
            action.setEnabled(True)

    def set_ms_only_mode(self, enabled: bool) -> None:
        """Enable or disable MS-only mode in the GUI.
        
        Args:
            enabled: True to enable MS-only mode, False for LC-MS mode.
        """
        self.processing_mode = (
            ProcessingMode.MS_ONLY if enabled else ProcessingMode.LC_MS
        )
        self.sync_mode_selection()
        self.ms_only_mode = enabled

        # Keep the individual controls in sync with their container.  While a
        # disabled parent normally disables its children automatically, setting
        # these explicitly ensures that no alignment control can retain a
        # disabled state after returning from MS-only mode.
        alignment_controls = (
            self.ms_ui.open_alignment_list,
            self.ms_ui.pushButton_delete_alignment,
            self.ms_ui.path_alignment_list,
            self.ms_ui.alignment_time_window,
            self.ms_ui.alignment_mz_window,
            self.ms_ui.alignment_min_peaks,
            self.ms_ui.alignment_sn_cutoff,
        )
        for control in alignment_controls:
            control.setEnabled(not enabled)
        
        if enabled:
            # MS-only mode: disable all LC-related features
            self.logger.info("Using MS-only mode")
            
            # Disable entire Alignment section with red text and hide spinbox values
            self.ms_ui.frame_alignment.setEnabled(False)
            self.ms_ui.frame_alignment.setStyleSheet(
                "QLabel { color: #a0a0a0; }"
                "QSpinBox, QDoubleSpinBox { color: transparent; }"
            )
            self.ms_ui.alignment_time_window.setToolTip("")
            self.ms_ui.alignment_mz_window.setToolTip("")
            self.ms_ui.alignment_min_peaks.setToolTip("")
            self.ms_ui.alignment_sn_cutoff.setToolTip("")
            
            # Disable sum spectrum resolution (LC-specific) and hide value
            self.ms_ui.sum_spectrum_resolution.setEnabled(False)
            self.ms_ui.sum_spectrum_resolution.setStyleSheet("color: transparent;")
            self.ms_ui.sum_spectrum_resolution.setToolTip("")
            self.ms_ui.label_resolution.setEnabled(False)
            self.ms_ui.label_resolution.setStyleSheet("color: #a0a0a0;")
            
            # Hide calibration table (not applicable in MS-only mode)
            self.ms_ui.tableWidget_calibration.setVisible(False)
            self.ms_ui.pushButton_apply_sn.setVisible(False)
            self.ms_ui.calibrant_sn_cutoff.setGeometry(
                self.ms_ui.calibrant_sn_cutoff.x(),
                self.ms_ui.calibrant_sn_cutoff.y(),
                221,
                self.ms_ui.calibrant_sn_cutoff.height()
            )
            self.ms_ui.label_calibrant_sn_cutoff.setText("Calibrant S/N cut-off")
            self.ms_ui.calibrant_sn_cutoff.setToolTip(
                "Minimum signal-to-noise required for a calibrant to be used."
            )
            
            # Disable "Quantify aligned files only" checkbox
            self.ms_ui.quantify_aligned.setEnabled(False)
            self.ms_ui.quantify_aligned.setChecked(False)
            self.ms_ui.quantify_aligned.setStyleSheet("color: #a0a0a0;")
            
        else:
            # LC-MS mode: enable all features
            self.logger.info("Using LC-MS mode")
            
            # Enable Alignment section and reset styling
            self.ms_ui.frame_alignment.setEnabled(True)
            self.ms_ui.frame_alignment.setStyleSheet("")
            self.ms_ui.alignment_time_window.setToolTip(
                "Time window used around each alignment feature to determine its "
                "observed \nretention time. "
                "Can be overwritten for individual features in the alignment file."
            )
            self.ms_ui.alignment_mz_window.setToolTip(
                "m/z window used around the exact m/z of an alignment feature\n"
                "when creating an extracted ion chromatogram. "
                "Can be overwritten\nfor individual features in the alignment file."
            )
            self.ms_ui.alignment_min_peaks.setToolTip(
                "Minimum number of alignment features to use when aligning a\n"
                "chromatogram. When less features have a S/N above the cut-off,\n"
                "alignment fails for the corresponding sample."
            )
            self.ms_ui.alignment_sn_cutoff.setToolTip(
                "Minimum signal-to-noise required for an alignment feature to be used.\n"
                "Can be overwritten for individual features in the alignment file."
            )
            
            # Enable sum spectrum resolution and reset styling
            self.ms_ui.sum_spectrum_resolution.setEnabled(True)
            self.ms_ui.sum_spectrum_resolution.setStyleSheet("")
            self.ms_ui.sum_spectrum_resolution.setToolTip(
                "Number of data points per m/z unit in an LC-MS spectrum."
            )
            self.ms_ui.label_resolution.setEnabled(True)
            self.ms_ui.label_resolution.setStyleSheet("")
            
            # Show and enable calibration table
            self.ms_ui.tableWidget_calibration.setVisible(True)
            self.ms_ui.tableWidget_calibration.setEnabled(True)
            self.ms_ui.tableWidget_calibration.setStyleSheet("")
            self.ms_ui.pushButton_apply_sn.setVisible(True)
            self.ms_ui.calibrant_sn_cutoff.setGeometry(
                self.ms_ui.calibrant_sn_cutoff.x(),
                self.ms_ui.calibrant_sn_cutoff.y(),
                73,
                self.ms_ui.calibrant_sn_cutoff.height()
            )
            self.ms_ui.label_calibrant_sn_cutoff.setText("Set all S/N cut-offs to:")
            self.ms_ui.calibrant_sn_cutoff.setToolTip(
                "Minimum signal-to-noise required for a calibrant to be used.\n"
                "Can be modified per retention time window in the table below."
            )
            
            # Enable "Quantify aligned files only" checkbox and reset styling
            self.ms_ui.quantify_aligned.setEnabled(True)
            self.ms_ui.quantify_aligned.setStyleSheet("")
            

    def set_ref_file_mode(self, enabled: bool) -> None:
        """Update controls whose values are encoded in a reference file.

        When a reference file is uploaded, its m/z windows, isotopic peaks,
        charge carriers, and mass modifiers have already been determined.
        Disable the corresponding GUI controls to make clear that changing
        them would not affect processing. Restore the controls when a regular
        analytes list is loaded or the file is cleared.

        Args:
            enabled: True to enter ref-file mode (controls disabled),
                False to restore normal mode (controls enabled).
        """
        self.ref_file_mode = enabled
        self.update_quantitation_window_state()
        self.ms_ui.comboBox_charge_carrier.setEnabled(not enabled)
        self.ms_ui.comboBox_mass_modifier.setEnabled(not enabled)
        dropdown_style = "color: transparent;" if enabled else ""
        self.ms_ui.comboBox_charge_carrier.setStyleSheet(dropdown_style)
        self.ms_ui.comboBox_mass_modifier.setStyleSheet(dropdown_style)
        self.ms_ui.label_charge_carrier.setEnabled(not enabled)
        self.ms_ui.label_mass_modifier.setEnabled(not enabled)
        dropdown_label_style = "color: #a0a0a0;" if enabled else ""
        self.ms_ui.label_charge_carrier.setStyleSheet(dropdown_label_style)
        self.ms_ui.label_mass_modifier.setStyleSheet(dropdown_label_style)
        if enabled:
            self.ms_ui.min_isotopic_fraction.setEnabled(False)
            self.ms_ui.min_isotopic_fraction.setStyleSheet("color: transparent;")
            self.ms_ui.min_isotopic_fraction.setToolTip("")
            self.ms_ui.label_isotopic_fraction.setEnabled(False)
            self.ms_ui.label_isotopic_fraction.setStyleSheet("color: #a0a0a0;")
        else:
            self.ms_ui.min_isotopic_fraction.setEnabled(True)
            self.ms_ui.min_isotopic_fraction.setStyleSheet("")
            self.ms_ui.min_isotopic_fraction.setToolTip(
                "Minimum fraction of the total isotopic pattern that should\n"
                "be integrated per analyte and charge state."
            )
            self.ms_ui.label_isotopic_fraction.setEnabled(True)
            self.ms_ui.label_isotopic_fraction.setStyleSheet("")

    def connect_signals(self) -> None:
        """Connect all UI signals to their handlers."""
        self.fld_ui.pushButton_start_processing.clicked.connect(
            self.batch_coordinator.start_fld_batch_process
        )
        self.ui.comboBox_processing_mode.currentTextChanged.connect(
            lambda text: self.set_processing_mode(ProcessingMode(text))
        )
        # File operation buttons.
        self.ms_ui.open_blocks_folder.clicked.connect(
            self.file_handlers.open_blocks_folder
        )
        self.ms_ui.open_alignment_list.clicked.connect(
            self.file_handlers.open_alignment_list
        )
        self.ms_ui.open_analytes_list.clicked.connect(
            self.file_handlers.open_analytes_list
        )
        self.ms_ui.open_mzxml_path.clicked.connect(
            self.file_handlers.open_mzxml_path
        )
        self.ms_ui.pushButton_start_processing.clicked.connect(
            self.batch_coordinator.start_batch_process
        )
        self.ms_ui.pushButton_apply_sn.clicked.connect(
            self.calibration_table_manager.apply_sn_cutoff
        )
        self.ms_ui.pushButton_delete_alignment.clicked.connect(
            self.file_handlers.clear_alignment_file
        )
        self.ms_ui.pushButton_delete_analytes.clicked.connect(
            self.file_handlers.clear_analytes_file
        )
        self.fld_ui.open_mzxml_path.clicked.connect(
            self.fld_form.select_raw_folder
        )
        self.fld_ui.open_peaks_list.clicked.connect(
            lambda: self.fld_form.select_list(
                self.fld_ui.path_peaks_list,
                "Select LC-FLD peaks list",
            )
        )
        self.fld_ui.open_alignment_list.clicked.connect(
            lambda: self.fld_form.select_list(
                self.fld_ui.path_alignment_list,
                "Select LC-FLD alignment list",
            )
        )
        self.fld_ui.pushButton_delete_peaks.clicked.connect(
            self.fld_ui.path_peaks_list.clear
        )
        self.fld_ui.pushButton_delete_alignment.clicked.connect(
            self.fld_ui.path_alignment_list.clear
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
        self.ui.actionLC_FLD_alignment_list.triggered.connect(
            self.download_fld_alignment_template
        )
        self.ui.actionLC_FLD_peaks_list.triggered.connect(
            self.download_fld_peaks_template
        )
        self.ui.actionVisualize_mass_spectrum.triggered.connect(
            lambda: launch_xy_viewer(self)
        )
        self.ui.actionView_LC_FLD_chromatogram.triggered.connect(
            lambda: launch_chromatogram_viewer(self)
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
        """Download LC-MS alignment template Excel file."""
        self.template_manager.download_template("lc_ms_alignment")

    def download_analytes_template(self) -> None:
        """Download (LC-)MS analytes template Excel file."""
        self.template_manager.download_template("ms_analytes")

    def download_block_template(self) -> None:
        """Download block file template."""
        self.template_manager.download_template("block")

    def download_fld_alignment_template(self) -> None:
        """Download LC-FLD alignment template Excel file."""
        self.template_manager.download_template("lc_fld_alignment")

    def download_fld_peaks_template(self) -> None:
        """Download LC-FLD peaks template Excel file."""
        self.template_manager.download_template("lc_fld_peaks")
    
    def report_a_bug(self) -> None:
        """Direct to SweetSuite issues page on GitHub."""
        webbrowser.open("https://github.com/stainawarijar/SweetSuite/issues")
