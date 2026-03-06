from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog

from ..widgets.scientific_spin_box import ScientificSpinBox
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
        self.promote_to_scientific_spinbox()
        self.setup_quadratic_toggle()
        self._setup_window_flags()
        self._connect_buttons()

    def _setup_window_flags(self) -> None:
        """Remove the X close button from the dialog."""
        self.dialog.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint
        )

    def _connect_buttons(self) -> None:
        """Connect OK and Cancel buttons to accept/reject."""
        self.ui.pushButton_apply_advanced_settings.clicked.connect(self.dialog.accept)
        self.ui.pushButton_cancel_advanced_settings.clicked.connect(self.dialog.reject)

    def _snapshot_settings(self) -> dict:
        """Capture current settings values for cancel/revert."""
        return {
            "quadratic": self.ui.checkBox_quadratic.isChecked(),
            "mz2": self.ui.doubleSpinBox_mz2.value(),
            "mz": self.ui.doubleSpinBox_mz.value(),
            "constant": self.ui.doubleSpinBox_constant.value(),
            "peak_heights": self.ui.checkBox_peakHeights.isChecked(),
            "save_xy": self.ui.checkBox_save_xy.isChecked(),
        }

    def _restore_settings(self, snapshot: dict) -> None:
        """Restore settings from a snapshot."""
        self.ui.checkBox_quadratic.setChecked(snapshot["quadratic"])
        self.ui.doubleSpinBox_mz2.setValue(snapshot["mz2"])
        self.ui.doubleSpinBox_mz.setValue(snapshot["mz"])
        self.ui.doubleSpinBox_constant.setValue(snapshot["constant"])
        self.ui.checkBox_peakHeights.setChecked(snapshot["peak_heights"])
        self.ui.checkBox_save_xy.setChecked(snapshot["save_xy"])

    def setup_quadratic_toggle(self) -> None:
        """Disable coefficient inputs until the quadratic checkbox is checked."""
        self._quadratic_widgets = [
            self.ui.doubleSpinBox_mz2,
            self.ui.doubleSpinBox_mz,
            self.ui.doubleSpinBox_constant,
            self.ui.label,
            self.ui.label_mz2,
            self.ui.label_mz2_2,
            self.ui.label_2,
            self.ui.label_3,
        ]
        # Set initial state based on checkbox
        checked = self.ui.checkBox_quadratic.isChecked()
        for widget in self._quadratic_widgets:
            widget.setEnabled(checked)
        # Connect checkbox to toggle handler
        self.ui.checkBox_quadratic.toggled.connect(self._on_quadratic_toggled)

    def _on_quadratic_toggled(self, checked: bool) -> None:
        """Enable or disable coefficient inputs when checkbox changes."""
        for widget in self._quadratic_widgets:
            widget.setEnabled(checked)

    def show_dialog(self) -> None:
        """Show the advanced settings dialog."""
        snapshot = self._snapshot_settings()
        result = self.dialog.exec()
        if result == QDialog.DialogCode.Rejected:
            self._restore_settings(snapshot)
    
    def promote_to_scientific_spinbox(self) -> None:
        """Enable scientific notation for the spinboxes inside 
        the advanced settings dialog. 
        """
        # List of (attribute name, range min, range max, default step)
        spinboxes = [
            ("doubleSpinBox_mz2", -1e3, 1e3, 1e-8),
            ("doubleSpinBox_mz", -1e3, 1e3, 1e-8),
            ("doubleSpinBox_constant", -1e3, 1e3, 1e-8),
        ]
        
        for name, minv, maxv, step in spinboxes:
            old = getattr(self.ui, name)
            layout = old.parentWidget().layout()
            
            if layout is None:  # fallback for absolute positioning
                # Get parent frame and replace in place
                parent = old.parentWidget()
                geo = old.geometry()
                old.hide()
                new = ScientificSpinBox(parent)
                new.setGeometry(geo)
            else:
                # If using layout, swap in layout
                index = layout.indexOf(old)
                layout.removeWidget(old)
                old.deleteLater()
                new = ScientificSpinBox()
                layout.insertWidget(index, new)
            
            new.setMinimum(minv)
            new.setMaximum(maxv)
            new.setSingleStep(step)
            new.setDecimals(10)
            new.setValue(old.value())
            new.setObjectName(name)
            setattr(self.ui, name, new)