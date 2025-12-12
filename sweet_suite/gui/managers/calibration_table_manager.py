import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QSpinBox, QTableWidgetItem
from PyQt6.QtGui import QIcon

from ...utils import utils


class CalibrationTableManager:
    """Handles calibration table population and operations."""
    
    def __init__(self, parent, ui):
        """Initialize calibration table manager.
        
        Args:
            parent: Parent widget (MainWindow)
            ui: Main window UI object
        """
        self.parent = parent
        self.ui = ui
        self.table = ui.tableWidget_calibration
    
    def apply_sn_cutoff(self) -> None:
        """Apply the S/N calibration cut-off to all table entries."""
        for row in range(self.table.rowCount()):
            spinbox = self.table.cellWidget(row, 3)
            if isinstance(spinbox, QSpinBox):
                spinbox.setValue(self.ui.calibrant_sn_cutoff.value())
    
    def update_table(self) -> None:
        """Populates the calibration table."""
        df = self.parent.analytes_list_df
        
        # Extract unique (time, time_window) combinations. 
        unique_combos = (
            df[["time", "time_window"]]
            .drop_duplicates()
            .reset_index(drop=True)
        )
        
        # Ensure column and row count in table.
        self.table.setRowCount(len(unique_combos))
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "Time (s)", "Window (s)", "Calibrate", "Calibrant S/N cut-off"
        ])
        
        # Set width of columns.
        self.table.setColumnWidth(0, 90)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 90)
        
        # Add edit icon to last column.
        edit_icon = utils.resource_path(os.path.join(
            "sweet_suite", "gui", "assets", "google-material-icons", "edit.svg"
        ))
        self.table.horizontalHeaderItem(3).setIcon(QIcon(edit_icon))
        
        # Up and down icons (normalize to forward slashes for Qt).
        up_icon = utils.resource_path(os.path.join(
            "sweet_suite", "gui", "assets", "google-material-icons", "up.svg"
        )).replace("\\", "/")
        down_icon = utils.resource_path(os.path.join(
            "sweet_suite", "gui", "assets", "google-material-icons", "down.svg"
        )).replace("\\", "/")
        
        # Populate the table, order from low to high time.
        sorted_combos = unique_combos.sort_values(by="time").reset_index(drop=True)
        for i, combo in sorted_combos.iterrows():
            time = float(combo["time"])
            time_window = float(combo["time_window"])
            combo_rows = df[
                (df["time"] == time) & (df["time_window"] == time_window)
            ]
            calibrants_present = combo_rows["calibrant"].notna().any()
            
            # Time/Window columns (centered).
            time_item = QTableWidgetItem(str(time))
            time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 0, time_item)
            window_item = QTableWidgetItem(str(time_window))
            window_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 1, window_item)
            
            # Calibration checkboxes (enable if calibrants present).
            checkbox = QCheckBox()
            checkbox.setChecked(bool(calibrants_present))
            checkbox.setEnabled(bool(calibrants_present))
            checkbox.setStyleSheet("""
                QCheckBox {
                    margin: 0px;
                    padding: 0px;
                }
                QCheckBox::indicator {
                    width: 100%;
                    height: 100%;
                    border: none;
                }
                QCheckBox::indicator:unchecked:enabled {
                    background-color: #ff4444;
                }
                QCheckBox::indicator:checked:enabled {
                    background-color: #4CAF50;
                }
                QCheckBox::indicator:unchecked:disabled {
                    background-color: #ff4444;
                }
                QCheckBox::indicator:checked:disabled {
                    background-color: #4CAF50;
                }
                QCheckBox::indicator:disabled {
                    background-color: #c0c0c0;
                }
            """)
            self.table.setCellWidget(i, 2, checkbox)
            
            # S/N cut-off spin box (enabled if calibrant present).
            spinbox = QSpinBox()
            spinbox.setValue(self.ui.calibrant_sn_cutoff.value())
            spinbox.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            spinbox.wheelEvent = lambda event: event.ignore()
            spinbox.setMinimum(0)
            spinbox.setMaximum(9999)
            self.table.setCellWidget(i, 3, spinbox)
            spinbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            if bool(calibrants_present):
                spinbox.setEnabled(True)
                spinbox.setStyleSheet(f"""
                    QSpinBox {{
                        border: 1px solid #c0c0c0;
                        border-radius: 2px;
                        padding: 2px;
                        background: white;
                    }}
                    QSpinBox::up-button {{
                        width: 15px;
                        height: 13px;
                        image: url("{up_icon}");
                        border: 1px solid #c0c0c0;
                        background-color: #e6e6e6;
                    }}
                    QSpinBox::down-button {{
                        width: 15px;
                        height: 13px;
                        image: url("{down_icon}");
                        border: 1px solid #c0c0c0;
                        background-color: #e6e6e6;
                    }}
                """)
            else:
                spinbox.setEnabled(False)
                spinbox.setStyleSheet("""
                    QSpinBox {
                        border: 1px solid #c0c0c0;
                        border-radius: 2px;
                        padding: 2px;
                        background: white;
                        color: white;
                    }
                    QSpinBox::up-button, QSpinBox::down-button {
                        width: 0px;
                        height: 0px;
                        border: none;
                    }
                """)
    
    def extract_calibration_data(self) -> dict:
        """Extract calibration table data into a dictionary. 
        
        Returns:
            Dictionary mapping (time, window) tuples to calibration settings.
        """
        sum_spectra_calibration = {}
        for row in range(self.table.rowCount()):
            try:
                time_value = float(self.table.item(row, 0).text())
                window = float(self.table.item(row, 1).text())
            except (AttributeError, ValueError):
                continue  # Skip rows with invalid data (should not happen).
            
            checkbox = self.table.cellWidget(row, 2)
            if isinstance(checkbox, QCheckBox):
                calibrate = checkbox.isChecked()
            
            spinbox = self.table.cellWidget(row, 3)
            if isinstance(spinbox, QSpinBox):
                sn_cutoff = spinbox.value()
            
            sum_spectra_calibration[(time_value, window)] = {
                "calibrate": calibrate,
                "sn_cutoff": sn_cutoff
            }
        
        return sum_spectra_calibration