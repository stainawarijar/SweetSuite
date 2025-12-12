import numpy as np
import pandas as pd
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from ..ui.ui_helpers import UIHelpers


class FileHandlers:
    """Handles file dialog operations and validation."""
    
    def __init__(self, parent, ui):
        """Initialize file handlers. 
        
        Args:
            parent: Parent widget (MainWindow).
            ui: Main window UI object.
        """
        self.parent = parent
        self.ui = ui
    
    def clear_alignment_file(self) -> None:
        """Clear the selected alignment file from the UI and internal state."""
        # Do nothing if no file was selected. 
        if self.parent.alignment_list_df is None:
            return
        
        # Set up confirmation box. 
        box = QMessageBox(self.parent)
        box.setWindowTitle("Clear alignment file")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(
            "This will clear the uploaded alignment file from the program.\n"
            "Do you want to continue?"
        )
        yes_button = box.addButton(
            "Yes, clear", QMessageBox.ButtonRole.YesRole
        )
        yes_button.setStyleSheet(
            "background-color: #8B0000; color: white; font-weight: bold;"
        )
        cancel_button = box.addButton(
            "Cancel", QMessageBox.ButtonRole.NoRole
        )
        box.setDefaultButton(cancel_button)
        box.exec()
        
        # Clear on confirmation.
        if box.clickedButton() == yes_button:
            self.ui.path_alignment_list.clear()
            self.parent.alignment_list_df = None
    
    def clear_analytes_file(self) -> None:
        """Clear the selected analytes file from the UI and internal state."""
        # Do nothing if no file was selected. 
        if self.parent.analytes_list_df is None:
            return
        
        # Set up confirmation box.
        msg_box = QMessageBox(self.parent)
        msg_box.setWindowTitle("Clear analytes list")
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setText(
            "This will clear the uploaded analytes list from the program.\n"
            "Do you want to continue?"
        )
        yes_button = msg_box.addButton(
            "Yes, clear", QMessageBox.ButtonRole.YesRole
        )
        yes_button.setStyleSheet(
            "background-color: #8B0000; color: white; font-weight: bold;"
        )
        cancel_button = msg_box.addButton(
            "Cancel", QMessageBox.ButtonRole.NoRole
        )
        msg_box.setDefaultButton(cancel_button)
        msg_box.exec()
        
        # Clear on confirmation.
        if msg_box.clickedButton() == yes_button:
            self.ui.path_analytes_list.clear()
            self.parent.analytes_list_df = None
            self.ui.tableWidget_calibration.setRowCount(0)
    
    def open_alignment_list(self) -> None:
        """Open file dialog for selecting an alignment list."""
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Select a '.xlsx' alignment file:",
            "",
            "Excel files (*.xlsx);;All Files (*)"
        )
        if not file_path:
            return
        
        # Add file path to UI. 
        self.ui.path_alignment_list.clear()
        self.ui.path_alignment_list.addItem(file_path)
        
        # Read Excel file as a Pandas dataframe.
        df = pd.read_excel(file_path)

        # Check structure of file.
        if not self.check_alignment_list(df):
            self.ui.path_alignment_list.clear()
            self.parent.alignment_list_df = None
            return
        
        # Remove all spaces (leading, trailing and internal) from string
        # entries. Convert empty strings to NaN.
        df["required"] = (
            df["required"].astype(str)
            .str.replace(r"\s+", "", regex=True)
        )
        df["required"] = df["required"].replace(["", "nan"], np.nan)
        
        # Update data container.
        self.parent.alignment_list_df = df
    
    def open_analytes_list(self) -> None:
        """Open file dialog for selecting an analytes list."""
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Select a '.xlsx' analytes list:",
            "",
            "Excel files (*.xlsx);;All Files (*)"
        )
        if not file_path:
            return
        
        # Add file path to UI.
        self.ui.path_analytes_list.clear()
        self.ui.path_analytes_list.addItem(file_path)
        
        # Read in the Excel file.
        df = pd.read_excel(file_path)

        # Check formatting of the list.
        if not self.check_analytes_list(df):
            self.ui.path_analytes_list.clear()
            self.parent.analytes_list_df = None
            self.ui.tableWidget_calibration.setRowCount(0)
            return
        
        # Update data container and table.
        self.parent.analytes_list_df = df
        self.parent.calibration_table_manager.update_table()

    def check_alignment_list(self, df: pd.DataFrame) -> bool:
        """Check structure of the alignment list.
        
        Looks for missing columns, missing values and incorrect data types.
        Also checks that there are at least 5 alignment features, and  that 
        all numeric entries are non-negative.

        Returns True if correctly formatted, False otherwise.
        """
        # Check for missing columns.
        columns_required = [
            "mz", "time", "mz_window", "time_window",
            "sn_cutoff", "required"
        ]
        if not set(df.columns) == set(columns_required):
            UIHelpers.show_message_box(
                self.parent,
                title="Incorrect formatting",
                text=(
                    "The alignment file should contain the following"
                    " columns: 'mz', 'time', 'mz_window', 'time_window',"
                    " 'sn_cutoff' and `required`."
                ),
                icon="Critical"
            )
            return False
        
        # Check for missing entries in required columns.
        missing_rows = (
            df[["mz", "time"]].isnull().any(axis=1)
            & df[["mz", "time"]].notnull().any(axis=1)
        )
        if missing_rows.any():
            UIHelpers.show_message_box(
                self.parent,
                title="Missing entries",
                text="Some rows have missing values in required columns.",
                informative_text=(
                    "If any of 'mz' or 'time' is filled for a row, "
                    "then both must be filled."
                ),
                icon="Critical"
            )
            return False
        
        # Check data types of columns and non-negativity.
        require_number = [
            # May be either int or float
            "mz", "time", "mz_window", "time_window", "sn_cutoff"
        ]
        for col in require_number:
            non_null = df[col].dropna()  # Other than 'mz' and 'time' can be empty
            if not pd.api.types.is_numeric_dtype(non_null):
                UIHelpers.show_message_box(
                    self.parent,
                    title="Incorrect data type",
                    text=f"Column '{col}' may contain only numeric values.",
                    icon="Critical"
                )
                return False
            
            # Check for non-negative values
            if (non_null < 0).any():
                UIHelpers.show_message_box(
                    self.parent,
                    title="Negative values detected",
                    text=f"Column '{col}' contains negative values.",
                    informative_text="All numeric entries must be non-negative.",
                    icon="Critical"
                )
                return False

        # Check for at least 5 alignment features.
        number = df.shape[0]
        if number < 5:
            UIHelpers.show_message_box(
                self.parent,
                title="Not enough alignment features",
                text=(
                    "At least 5 alignment features are required, "
                    f"but your file contains only {number}."
                ),
                informative_text="Add more alignment features to your file.",
                icon="Warning"
            )

        return True

    def check_analytes_list(self, df: pd.DataFrame) -> bool:
        """Check structure of the analytes list.

        Looks for missing columns, missing values and incorrect data types.
        Also checks that all numeric values are non-negative.
        
        Returns True if correctly formatted, False otherwise.
        """
        # Check required columns. `mz_window` is optional.
        columns_required = [
            "analyte", "charge_min", "charge_max",
            "calibrant", "time", "time_window", "mz_window"
        ]
        columns_check = [col for col in df.columns]
        
        if sorted(columns_check) != sorted(columns_required):
            UIHelpers.show_message_box(
                self.parent,
                title="Incorrect formatting",
                text="The analytes list must contain the following columns:",
                informative_text=(
                    "`analyte`, `charge_min`, `charge_max`, `calibrant`"
                    ", `time`, `time_window` and `mz_window`."
                ),
                icon="Critical"
            )
            return False
        
        # Check for missing entries in required columns.
        required_cols = [
            "analyte", "charge_min", "charge_max", "time", "time_window"
        ]
        missing_rows = (
            df[required_cols].isnull().any(axis=1)
            & df[required_cols].notnull().any(axis=1)
        )
        if missing_rows.any():
            UIHelpers.show_message_box(
                self.parent,
                title="Missing entries",
                text="Some rows have missing values in required columns.",
                informative_text=(
                    "If any of 'analyte', 'charge_min', 'charge_max', 'time', "
                    "or 'time_window' is filled for a row, all must be filled."
                ),
                icon="Critical"
            )
            return False

        # Check for duplicate analyte entries
        if df["analyte"].duplicated().any():
            UIHelpers.show_message_box(
                self.parent,
                title="Duplicate analytes",
                text="The analytes list contains duplicate 'analyte' entries.",
                informative_text="Adjust your file.",
                icon="Critical"
            )
            return False

        # Check data types of columns.
        # 'calibrant' is not checked, any value inside it is considered "True".
        require_string = ["analyte"]
        require_int = ["charge_min", "charge_max"]
        require_number = ["time", "time_window", "mz_window"]  # int or float

        for col in require_string:
            if not pd.api.types.is_string_dtype(df[col]):
                UIHelpers.show_message_box(
                    self.parent,
                    title="Incorrect data type",
                    text=f"Column '{col}' must contain only string values.",
                    icon="Critical"
                )
                return False
        
        for col in require_int:
            if not pd.api.types.is_integer_dtype(df[col]):
                UIHelpers.show_message_box(
                    self.parent,
                    title="Incorrect data type",
                    text=f"Column '{col}' must contain only integer values.",
                    icon="Critical"
                )
                return False
        
        for col in require_number:
            non_null = df[col].dropna()  # 'mz_window' can be empty. 
            if not pd.api.types.is_numeric_dtype(non_null):
                UIHelpers.show_message_box(
                    self.parent,
                    title="Incorrect data type",
                    text=f"Column '{col}' may contain only numeric values.",
                    icon="Critical"
                )
                return False
            # Check for non-negative values
            if (non_null < 0).any():
                UIHelpers.show_message_box(
                    self.parent,
                    title="Negative values detected",
                    text=f"Column '{col}' contains negative values.",
                    informative_text="All numeric entries must be non-negative.",
                    icon="Critical"
                )
                return False

        # Check that charge_max >= charge_min for each row
        invalid_charge = df["charge_max"] < df["charge_min"]
        if invalid_charge.any():
            UIHelpers.show_message_box(
                self.parent,
                title="Invalid charge range",
                text="Some rows have 'charge_max' less than 'charge_min'.",
                informative_text="Adjust your file.",
                icon="Critical"
            )
            return False
        
        return True

    def open_blocks_folder(self) -> None:
        """Open file dialog for selecting a folder containing block files."""
        folder_path = QFileDialog.getExistingDirectory(
            None, "Select folder containing .block files:"
        )
        if not folder_path:
            return
        
        if self.ui.path_blocks.count() > 0:
            self.ui.path_blocks.clear()
        self.ui.path_blocks.addItem(folder_path)
        self.parent.update_charge_carriers()
    
    def open_mzxml_path(self) -> None:
        """Open file dialog for selecting a folder with mzXML files."""
        mzxml_path = QFileDialog.getExistingDirectory(
            None, "Select folder containing mzXML files:"
        )
        if not mzxml_path:
            return
        
        # Clear existing entry.
        if self.ui.path_mzxml.count() > 0:
            self.ui.path_mzxml.clear()
        self.ui.path_mzxml.addItem(mzxml_path)