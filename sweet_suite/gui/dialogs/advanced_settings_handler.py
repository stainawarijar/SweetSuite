from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog

from ..qtdesigner_files.gui_advanced_settings import Ui_advanced_settings


class AdvancedSettingsHandler:
    """Handles advanced settings dialog setup and operations."""
    
    def __init__(self, parent):
        """Initialize advanced settings handler. 
        
        Args:
            parent: Parent widget (MainWindow)
        """
        self.parent = parent
        
        # Initialize advanced settings dialog
        self.dialog = QDialog(parent)
        self.ui = Ui_advanced_settings()
        self.ui.setupUi(self.dialog)
        self.setup_quadratic_toggle()
        self.setup_window_flags()
        self.connect_buttons()

    def setup_window_flags(self) -> None:
        """Remove the X close button from the dialog."""
        self.dialog.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint
        )

    def connect_buttons(self) -> None:
        """Connect OK and Cancel buttons to accept/reject."""
        self.ui.pushButton_apply_advanced_settings.clicked.connect(self.dialog.accept)
        self.ui.pushButton_cancel_advanced_settings.clicked.connect(self.dialog.reject)

    def snapshot_settings(self) -> dict:
        """Capture current settings values for cancel/revert."""
        return {
            "quadratic": self.ui.checkBox_quadratic.isChecked(),
            "mz2_coeff": self.ui.mz2_coeff.value(),
            "mz2_exp": self.ui.mz2_exponent.value(),
            "mz_coeff": self.ui.mz_coeff.value(),
            "mz_exp": self.ui.mz_exponent.value(),
            "constant_coeff": self.ui.constant_coeff.value(),
            "constant_exp": self.ui.constant_exponent.value(),
            "peak_heights": self.ui.checkBox_peakHeights.isChecked(),
            "save_xy": self.ui.checkBox_save_xy.isChecked(),
        }

    def restore_settings(self, snapshot: dict) -> None:
        """Restore settings from a snapshot."""
        self.ui.checkBox_quadratic.setChecked(snapshot["quadratic"])
        self.ui.mz2_coeff.setValue(snapshot["mz2_coeff"])
        self.ui.mz2_exponent.setValue(snapshot["mz2_exp"])
        self.ui.mz_coeff.setValue(snapshot["mz_coeff"])
        self.ui.mz_exponent.setValue(snapshot["mz_exp"])
        self.ui.constant_coeff.setValue(snapshot["constant_coeff"])
        self.ui.constant_exponent.setValue(snapshot["constant_exp"])
        self.ui.checkBox_peakHeights.setChecked(snapshot["peak_heights"])
        self.ui.checkBox_save_xy.setChecked(snapshot["save_xy"])

    def setup_quadratic_toggle(self) -> None:
        """Disable coefficient inputs until the quadratic checkbox is checked."""
        self.quadratic_widgets = [
            self.ui.mz2_coeff,
            self.ui.mz2_exponent,
            self.ui.mz_coeff,
            self.ui.mz_exponent,
            self.ui.constant_coeff,
            self.ui.constant_exponent,
            self.ui.label,
            self.ui.label_10_a,
            self.ui.label_10_b,
            self.ui.label_10_c,
            self.ui.label_mz2,
            self.ui.label_mz,
            self.ui.label_2,
            self.ui.label_3,
        ]
        # Set initial state based on checkbox
        checked = self.ui.checkBox_quadratic.isChecked()
        for widget in self.quadratic_widgets:
            widget.setEnabled(checked)
        # Connect checkbox to toggle handler
        self.ui.checkBox_quadratic.toggled.connect(self.on_quadratic_toggled)

    def on_quadratic_toggled(self, checked: bool) -> None:
        """Enable or disable coefficient inputs when checkbox changes."""
        for widget in self.quadratic_widgets:
            widget.setEnabled(checked)

    def show_dialog(self) -> None:
        """Show the advanced settings dialog."""
        snapshot = self.snapshot_settings()
        result = self.dialog.exec()
        if result == QDialog.DialogCode.Rejected:
            self.restore_settings(snapshot)
    
