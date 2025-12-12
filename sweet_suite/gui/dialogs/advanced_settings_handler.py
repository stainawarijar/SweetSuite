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
    
    def show_dialog(self) -> None:
        """Show the advanced settings dialog."""
        self.dialog.exec()
    
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