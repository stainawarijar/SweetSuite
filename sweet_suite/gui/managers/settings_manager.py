import os
from datetime import datetime

import pandas as pd
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from ..ui.ui_helpers import UIHelpers
from ...utils import utils


class SettingsManager:
    """Handles settings import, export, and reset operations."""
    
    def __init__(self, parent, ui, advanced_ui):
        """Initialize settings manager.
        
        Args:
            parent: Parent widget (MainWindow).
            ui: Main window UI object.
            advanced_ui: Advanced settings UI object.
        """
        self.parent = parent
        self.ui = ui
        self.advanced_ui = advanced_ui
    
    def export_settings(self) -> None:
        """Export all settings to a CSV file, with option to rename."""
        current_datetime = datetime.now().strftime("%d-%m-%Y_%H%M")
        default_filename = f"{current_datetime}_sweet_suite_settings.csv"
        save_path, _ = QFileDialog.getSaveFileName(
            self.parent,
            "Export settings to CSV",
            os.path.join(os.getcwd(), default_filename),
            "CSV files (*.csv);;All Files (*)"
        )
        if not save_path:
            return
        
        settings = self.collect_settings()
        
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write("Setting,Value\n")
                for key, value in settings.items():
                    f.write(f"{key},{value}\n")
            
            UIHelpers.show_message_box(
                self.parent,
                title="Settings exported",
                text="Settings exported to:",
                informative_text=save_path,
                icon="Information"
            )

        except Exception as e:
            UIHelpers.show_message_box(
                self.parent,
                title="Error exporting settings",
                text="Could not export settings.",
                informative_text=str(e),
                icon="Critical"
            )
    
    def import_settings(self, csv_path: str = None) -> None:
        """Import settings from a CSV file and apply to the GUI. 
        
        Args:
            csv_path: Path to CSV file (optional). If not specified, a dialog 
            is opened to select a file.
        
        Keep existing values if a setting is missing from the CSV file.
        """
        if not csv_path:
            file_path, _ = QFileDialog.getOpenFileName(
                self.parent, 
                "Select settings CSV file", 
                "", 
                "CSV files (*.csv);;All Files (*)"
            )
            if not file_path:
                return
        else:
            file_path = csv_path
        
        try:
            settings = (
                pd.read_csv(file_path, index_col="Setting")
                ["Value"]
                .to_dict()
            )

        except Exception as e:
            UIHelpers.show_message_box(
                self.parent,
                title="Error importing settings",
                text="Could not read settings file.",
                informative_text=str(e),
                icon="Critical"
            )
            return
        
        try:
            self.apply_settings(settings)
            
            if not csv_path:
                UIHelpers.show_message_box(
                    self.parent,
                    title="Settings imported",
                    text="Settings imported successfully.",
                    informative_text=os.path.basename(file_path),
                    icon="Information"
                )
                
        except Exception as e:
            UIHelpers.show_message_box(
                self.parent,
                title="Error applying settings",
                text="Unexpected error while importing settings:",
                informative_text=str(e),
                icon="Critical"
            )
    
    def reset_settings(self) -> None:
        """Revert to default settings via CSV file, with confirmation."""
        msg_box = QMessageBox(self.parent)
        msg_box.setWindowTitle("Revert to default settings")
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setText(
            "This will reset all settings to their default values.\n"
            "Do you want to continue?"
        )
        yes_button = msg_box.addButton(
            "Yes, revert", QMessageBox.ButtonRole.YesRole
        )
        cancel_button = msg_box.addButton(
            "Cancel", QMessageBox.ButtonRole.NoRole
        )
        msg_box.setDefaultButton(cancel_button)
        msg_box.exec()
        
        if msg_box.clickedButton() == yes_button:
            default_settings_path = utils.resource_path(os.path.join(
                "sweet_suite", "resources", "templates", "default_settings.csv"
            ))
            self.import_settings(csv_path=default_settings_path)
    
    def collect_settings(self) -> dict:
        """Extract settings from GUI widgets. 
        
        Returns:
            Dictionary containing all current settings.
        """
        return {
            # Alignment settings
            "alignment_time_window": float(
                self.ui.alignment_time_window.value()
            ),
            "alignment_mz_window": float(
                self.ui.alignment_mz_window.value()
            ),
            "alignment_sn_cutoff": int(
                self.ui.alignment_sn_cutoff.value()
            ),
            "alignment_min_peaks": int(
                self.ui.alignment_min_peaks.value()
            ),
            # Calibration and Quantitation settings
            "sum_spectrum_resolution": int(
                self.ui.sum_spectrum_resolution.value()
            ),
            "background_mass_window": float(
                self.ui.background_mass_window.value()
            ),
            "calibration_mass_window": float(
                self.ui.calibration_mass_window.value()
            ),
            "quantitation_mz_window": float(
                self.ui.quantitation_mz_window.value()
            ),
            "min_calibrant_number": int(
                self.ui.min_calibrant_number.value()
            ),
            "min_isotopic_fraction": float(
                self.ui.min_isotopic_fraction.value()
            ),
            "quantitate_aligned_only": bool(
                self.ui.quantify_aligned.isChecked()
            ),
            # Advanced settings
            "quadratic_mass_window": bool(
                self.advanced_ui.checkBox_quadratic.isChecked()
            ),
            "quadratic_mz2": float(
                self.advanced_ui.doubleSpinBox_mz2.value()
            ),
            "quadratic_mz": float(
                self.advanced_ui.doubleSpinBox_mz.value()
            ),
            "quadratic_constant": float(
                self.advanced_ui.doubleSpinBox_constant.value()
            )
        }
    
    def apply_settings(self, settings: dict) -> None:
        """Apply settings to GUI widgets.
        
        Args:
            settings: Dictionary of settings to apply.
        """
        # Alignment settings
        self.ui.alignment_time_window.setValue(float(settings.get(
            "alignment_time_window", self.ui.alignment_time_window.value()
        )))
        self.ui.alignment_mz_window.setValue(float(settings.get(
            "alignment_mz_window", self.ui.alignment_mz_window.value()
        )))
        self.ui.alignment_sn_cutoff.setValue(int(settings.get(
            "alignment_sn_cutoff", self.ui.alignment_sn_cutoff.value()
        )))
        self.ui.alignment_min_peaks.setValue(int(settings.get(
            "alignment_min_peaks", self.ui.alignment_min_peaks.value()
        )))
        
        # Calibration and Quantitation settings
        self.ui.sum_spectrum_resolution.setValue(int(settings.get(
            "sum_spectrum_resolution", self.ui.sum_spectrum_resolution.value()
        )))
        self.ui.background_mass_window.setValue(float(settings.get(
            "background_mass_window", self.ui.background_mass_window.value()
        )))
        self.ui.calibration_mass_window.setValue(float(settings.get(
            "calibration_mass_window", self.ui.calibration_mass_window.value()
        )))
        self.ui.quantitation_mz_window.setValue(float(settings.get(
            "quantitation_mz_window", self.ui.quantitation_mz_window.value()
        )))
        self.ui.min_calibrant_number.setValue(int(settings.get(
            "min_calibrant_number", self.ui.min_calibrant_number.value()
        )))
        self.ui.min_isotopic_fraction.setValue(float(settings.get(
            "min_isotopic_fraction", self.ui.min_isotopic_fraction.value()
        )))
        self.ui.quantify_aligned.setChecked(bool(eval(str(settings.get(
            "quantitate_aligned_only", self.ui.quantify_aligned.isChecked()
        )))))
        
        # Advanced settings
        self.advanced_ui.checkBox_quadratic.setChecked(bool(eval(str(settings.get(
            "quadratic_mass_window", self.advanced_ui.checkBox_quadratic.isChecked()
        )))))
        self.advanced_ui.doubleSpinBox_mz2.setValue(float(settings.get(
            "quadratic_mz2", self.advanced_ui.doubleSpinBox_mz2.value()
        )))
        self.advanced_ui.doubleSpinBox_mz.setValue(float(settings.get(
            "quadratic_mz", self.advanced_ui.doubleSpinBox_mz.value()
        )))
        self.advanced_ui.doubleSpinBox_constant.setValue(float(settings.get(
            "quadratic_constant", self.advanced_ui.doubleSpinBox_constant.value()
        )))