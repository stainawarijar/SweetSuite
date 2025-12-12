import time

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtWidgets import QDialog, QMessageBox, QListWidgetItem

from ..qtdesigner_files.batch_status import Ui_batch_status
from ...utils import utils
from ..ui.ui_helpers import UIHelpers
from ..workers.batch_worker import BatchWorker


class BatchCoordinator:
    """Handles batch processing workflow and coordination."""
    
    def __init__(self, parent, ui, advanced_ui, logger):
        """Initialize batch coordinator. 
        
        Args:
            parent: Parent widget (MainWindow).
            ui: Main window UI object.
            advanced_ui: Advanced settings UI object.
            logger: Logger instance.
        """
        self.parent = parent
        self.ui = ui
        self.advanced_ui = advanced_ui
        self.logger = logger
        
        # Batch processing state
        self.batch_start_time = None
        self.batch_worker = None
        self.batch_thread = None
        
        # Setup batch progress dialog
        self.batch_dialog = QDialog()
        self.batch_dialog.setModal(True)
        self.batch_dialog.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint
        )
        self.batch_ui = Ui_batch_status()
        self.batch_ui.setupUi(self.batch_dialog)
        self.batch_dialog.setFixedSize(291, 199)
        self.batch_ui.pushButton.clicked.connect(self.stop_batch_process)
        self.batch_ui.pushButton.setAutoDefault(False)
        self.batch_ui.pushButton.setDefault(False)
    
    def start_batch_process(self) -> None:
        """Start batch processing of the mzXML files."""
        # Disable all widgets to prevent settings from changing
        self.parent.setEnabled(False)
        
        # Parse the blocks again in case the folder was modified
        blocks_dict = self.parent.block_parser.parse_blocks()
        self.parent.blocks = blocks_dict
        
        # Determine charge carrier
        selected = self.ui.comboBox_charge_carrier.currentText()
        if selected != "":
            charge_carrier = selected.split("(")[0].strip()
        else:
            UIHelpers.show_message_box(
                self.parent,
                title="Missing charge carrier",
                text="Select a valid charge carrier block.",
                informative_text="",
                icon="Critical"
            )
            self.parent.setEnabled(True)
            return
        
        # Check if analytes and/or alignment file was uploaded
        analytes_list = self.ui.path_analytes_list.item(0)
        alignment_list = self.ui.path_alignment_list.item(0)
        if analytes_list is None and alignment_list is None:
            UIHelpers.show_message_box(
                self.parent,
                title="Missing files",
                text="Upload an analytes list and/or an alignment list.",
                informative_text="",
                icon="Warning"
            )
            self.parent.setEnabled(True)
            return
        
        # Ask for confirmation
        if not self.confirm_batch_start(analytes_list, alignment_list):
            self.parent.setEnabled(True)
            return
        
        # Start timer
        self.batch_start_time = time.perf_counter()
        
        # Extract calibration table data
        sum_spectra_calibration = (
            self.parent.calibration_table_manager.extract_calibration_data()
        )
        
        # Check batch directory path
        try:
            mzxml_folder_path = self.ui.path_mzxml.item(0).text()
        except AttributeError:
            mzxml_folder_path = None
        
        # Set up batch worker
        self.batch_worker = BatchWorker(
            blocks=self.parent.blocks,
            mzxml_folder_path=mzxml_folder_path,
            # Alignment settings
            alignment_list_df=self.parent.alignment_list_df,
            alignment_time_window=float(self.ui.alignment_time_window.value()),
            alignment_mz_window=float(self.ui.alignment_mz_window.value()),
            alignment_sn_cutoff=float(self.ui.alignment_sn_cutoff.value()),
            alignment_min_peaks=int(self.ui.alignment_min_peaks.value()),
            # Calibration & Quantitation settings
            sum_spectra_calibration=sum_spectra_calibration,
            charge_carrier=charge_carrier,
            analytes_list_df=self.parent.analytes_list_df,
            sum_spectrum_resolution=int(self.ui.sum_spectrum_resolution.value()),
            background_mass_window=float(self.ui.background_mass_window.value()),
            calibration_mass_window=float(self.ui.calibration_mass_window.value()),
            quantitation_mz_window=float(self.ui.quantitation_mz_window.value()),
            min_calibrant_number=int(self.ui.min_calibrant_number.value()),
            min_isotopic_fraction=float(self.ui.min_isotopic_fraction.value()),
            quantitate_aligned_only=self.ui.quantify_aligned.isChecked(),
            # Advanced settings
            quadratic_mz_window=bool(self.advanced_ui.checkBox_quadratic.isChecked()),
            quadratic_coeffs=(
                float(self.advanced_ui.doubleSpinBox_mz2.value()),
                float(self.advanced_ui.doubleSpinBox_mz.value()),
                float(self.advanced_ui.doubleSpinBox_constant.value())
            )
        )
        # Move batch worker to thread
        self.batch_thread = QThread()
        self.batch_worker.moveToThread(self.batch_thread)
        
        # Thread lifecycle signals
        self.batch_thread.started.connect(self.batch_worker.run)
        self.batch_thread.finished.connect(self.batch_thread.deleteLater)
        # Worker finished signal
        self.batch_worker.finished.connect(self.batch_thread.quit)
        self.batch_worker.finished.connect(self.batch_worker.deleteLater)
        self.batch_worker.finished.connect(self.on_batch_finished)
        # Worker aborted signal
        self.batch_worker.aborted.connect(self.batch_thread.quit)
        self.batch_worker.aborted.connect(self.batch_worker.deleteLater)
        self.batch_worker.aborted.connect(self.on_batch_aborted)
        # Worker error signal
        self.batch_worker.error.connect(self.batch_thread.quit)
        self.batch_worker.error.connect(self.batch_worker.deleteLater)
        self.batch_worker.error.connect(self.on_batch_error)
        # Progress signals
        self.batch_worker.ref_progress.connect(self.on_ref_progress_update)
        self.batch_worker.alignment_progress.connect(self.on_alignment_progress_update)
        self.batch_worker.quantitation_progress.connect(self.on_quantitation_progress_update)
        
        # Initiate batch progress dialog
        self.setup_progress_dialog()
        self.batch_dialog.show()
        
        # Start the thread
        self.batch_thread.start()
    
    def stop_batch_process(self) -> None:
        """Abort the batch process once the current file is processed, after
        confirmation by the user.
        """
        # Confirm abort to prevent accidental cancellation
        box = QMessageBox(self.parent)
        box.setWindowTitle("Confirm abort")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText("Do you want to abort the batch process?")
        box.setInformativeText(
            "The batch process will stop after the current file has been" \
            "fully processed."
        )
        yes_button = box.addButton("Yes, abort", QMessageBox.ButtonRole.YesRole)
        yes_button.setStyleSheet(
            "background-color: #8B0000; color: white; font-weight: bold;"
        )
        cancel_button = box.addButton("Cancel", QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(cancel_button)
        box.exec()
        
        if box.clickedButton() != yes_button:
            return
    
        if hasattr(self, "batch_worker") and self.batch_worker is not None:
            self.batch_ui.label_processing.setText("Aborting batch process...")
            self.batch_ui.pushButton.setEnabled(False)
            self.batch_worker.stop()
    
    def confirm_batch_start(
            self,
            analytes_list: QListWidgetItem | None,
            alignment_list: QListWidgetItem | None
    ) -> bool:
        """Ask for confirmation before starting batch process. 
        
        Args:
            analytes_list: Analytes list item (or None).
            alignment_list: Alignment list item (or None).
        
        Returns:
            True if user confirmed, False otherwise.
        """
        if analytes_list and alignment_list:
            message = (
                "This will perform alignment and quantitation.\n"
                "Do you want to continue?"
            )
        elif analytes_list:
            message = (
                "This will perform quantitation and no alignment.\n"
                "Do you want to continue?"
            )
        else:
            message = (
                "This will perform alignment and no quantitation.\n"
                "Do you want to continue?"
            )
        
        msg_box = QMessageBox(self.parent)
        msg_box.setWindowTitle("Start batch process")
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setText(message)
        yes_button = msg_box.addButton("Yes, start", QMessageBox.ButtonRole.YesRole)
        yes_button.setStyleSheet(
            "background-color: #237804; color: white; font-weight: bold;"
        )
        cancel_button = msg_box.addButton("Cancel", QMessageBox.ButtonRole.NoRole)
        msg_box.setDefaultButton(cancel_button)
        msg_box.exec()
        
        return msg_box.clickedButton() == yes_button
    
    def setup_progress_dialog(self) -> None:
        """Setup the batch progress dialog with initial state."""
        self.batch_ui.pushButton.setEnabled(True)
        self.batch_ui.label_processing.setText("Processing files...")
        
        if self.parent.analytes_list_df is None:
            self.batch_ui.progressBar_analytes_ref.setFormat("Not performed")
            self.batch_ui.progressBar_quantitation.setFormat("Not performed")
        else:
            self.batch_ui.progressBar_analytes_ref.setValue(0)
            self.batch_ui.progressBar_quantitation.setValue(0)
            self.batch_ui.progressBar_analytes_ref.setFormat("%p%")
            self.batch_ui.progressBar_quantitation.setFormat("%p%")
        
        if self.parent.alignment_list_df is None:
            self.batch_ui.progressBar_alignment.setFormat("Not performed")
        else:
            self.batch_ui.progressBar_alignment.setValue(0)
            self.batch_ui.progressBar_alignment.setFormat("%p%")
    
    # Progress update handlers
    def on_ref_progress_update(self, percent: int) -> None:
        """Update reference file progress bar in batch status dialog."""
        if self.batch_dialog.isVisible():
            self.batch_ui.progressBar_analytes_ref.setValue(percent)
    
    def on_alignment_progress_update(self, percent: int) -> None:
        """Update alignment progress bar in the batch status dialog."""
        if self.batch_dialog.isVisible():
            self.batch_ui.progressBar_alignment.setValue(percent)
    
    def on_quantitation_progress_update(self, percent: int) -> None:
        """Update quantitation progress bar in the batch status dialog."""
        if self.batch_dialog.isVisible():
            self.batch_ui.progressBar_quantitation.setValue(percent)
    
    # Event handlers
    def on_batch_error(
            self,
            title: str,
            text: str,
            informative_text: str,
            icon: str
    ) -> None:
        """Handle errors from the batch worker."""
        self.logger.error(f"Batch error: {title} - {text} - {informative_text}")
        self.batch_dialog.close()
        UIHelpers.show_message_box(self.parent, title, text, informative_text, icon)
        self.parent.setEnabled(True)
    
    def on_batch_aborted(self) -> None:
        """Handle batch processing abortion."""
        self.logger.warning("Batch processing aborted by user.")
        self.batch_dialog.close()
        UIHelpers.show_message_box(
            self.parent,
            title="Aborted",
            text="Batch processing aborted by user.",
            informative_text=utils.format_execution_time(
                self.batch_start_time, time.perf_counter()
            ),
            icon="Information"
        )
        self.parent.setEnabled(True)
    
    def on_batch_finished(self, success: bool) -> None:
        """Handle batch processing completion.
        
        Args:
            success: True if batch process fully completed without errors. 
        """
        self.logger.info("Batch processing finished")
        self.batch_dialog.close()
        if success:
            UIHelpers.show_message_box(
                self.parent,
                title="Finished batch process",
                text="Batch processing finished.",
                informative_text=utils.format_execution_time(
                    self.batch_start_time, time.perf_counter()
                ),
                icon="Information"
            )
        self.parent.setEnabled(True)