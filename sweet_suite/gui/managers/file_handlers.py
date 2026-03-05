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
        """Clear the selected analytes list or reference file from the UI and
        internal state."""
        # Do nothing if no file was selected.
        if self.parent.analytes_list_df is None and self.parent.analytes_ref_df is None:
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
            self.parent.analytes_ref_df = None
            self.ui.tableWidget_calibration.setRowCount(0)
            # Reset to LC-MS mode when analyte file is cleared
            self.parent.set_ms_only_mode(False)
    
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
        # Replace empty strings and "nan" strings with actual NaN.
        # Using mask() avoids the pandas FutureWarning about deprecated
        # downcasting behavior in replace().
        df["required"] = df["required"].mask(df["required"].isin(["", "nan"]))
        
        # Update data container.
        self.parent.alignment_list_df = df
    
    def open_analytes_list(self) -> None:
        """Open file dialog for selecting an analytes list or reference file."""
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Select a '.xlsx' analytes list or reference file:",
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

        # Determine which format the file matches by inspecting its columns.
        _ANALYTES_COLS = {
            "analyte", "charge_min", "charge_max",
            "calibrant", "time", "time_window", "mz_window"
        }
        _REF_COLS = {
            "peak", "charge_carrier", "mass_modifier", "mz", "relative_area",
            "mz_window", "time", "time_window", "calibrant"
        }
        file_cols = set(df.columns)

        if file_cols == _ANALYTES_COLS:
            # Validate as analytes list (shows error popups on failure).
            if not self.check_analytes_list(df):
                self.ui.path_analytes_list.clear()
                self.parent.analytes_list_df = None
                self.parent.analytes_ref_df = None
                self.ui.tableWidget_calibration.setRowCount(0)
                return
            # Store and populate calibration table.
            self.parent.analytes_list_df = df
            self.parent.analytes_ref_df = None
            self.parent.calibration_table_manager.update_table()

        elif file_cols == _REF_COLS:
            # Validate as reference file (shows error popups on failure).
            if not self.check_ref_file(df):
                self.ui.path_analytes_list.clear()
                self.parent.analytes_list_df = None
                self.parent.analytes_ref_df = None
                self.ui.tableWidget_calibration.setRowCount(0)
                return
            self._apply_ref_file(df)

        else:
            # Column set does not match either known format.
            UIHelpers.show_message_box(
                self.parent,
                title="Unrecognized file format",
                text="The uploaded file is neither a valid analytes list nor a valid reference file.",
                informative_text=(
                    "An analytes list must have columns: "
                    "'analyte', 'charge_min', 'charge_max', 'calibrant', "
                    "'time', 'time_window', 'mz_window'. "
                    "A reference file must have columns: "
                    "'peak', 'charge_carrier', 'mass_modifier', 'mz', 'relative_area', "
                    "'mz_window', 'time', 'time_window', 'calibrant'."
                ),
                icon="Critical"
            )
            self.ui.path_analytes_list.clear()
            self.parent.analytes_list_df = None
            self.parent.analytes_ref_df = None
            self.ui.tableWidget_calibration.setRowCount(0)
            self.parent.set_ms_only_mode(False)

    def check_ref_file(self, df: pd.DataFrame) -> bool:
        """Check the structure of an analytes reference file.

        Validates column presence, data types, completeness of required
        columns, and time/time_window consistency (either both entirely
        filled or both entirely empty).

        Returns True if correctly formatted, False otherwise.
        """
        # Required columns are already guaranteed by the caller (column-set
        # routing in open_analytes_list), but we re-check here defensively.
        columns_required = {
            "peak", "charge_carrier", "mass_modifier", "mz", "relative_area",
            "mz_window", "time", "time_window", "calibrant"
        }
        if set(df.columns) != columns_required:
            UIHelpers.show_message_box(
                self.parent,
                title="Incorrect formatting",
                text="The reference file must contain the following columns:",
                informative_text=(
                    "'peak', 'charge_carrier', 'mass_modifier', 'mz', 'relative_area', "
                    "'mz_window', 'time', 'time_window' and 'calibrant'."
                ),
                icon="Critical"
            )
            return False

        # Columns that must never contain missing values.
        always_required = ["peak", "charge_carrier", "mass_modifier", "mz", "relative_area", "mz_window", "calibrant"]
        for col in always_required:
            if df[col].isnull().any():
                UIHelpers.show_message_box(
                    self.parent,
                    title="Missing values",
                    text=f"Column '{col}' must not contain any missing values.",
                    icon="Critical"
                )
                return False

        # Data type checks.
        for col in ["peak", "charge_carrier", "mass_modifier"]:
            if not pd.api.types.is_string_dtype(df[col]):
                UIHelpers.show_message_box(
                    self.parent,
                    title="Incorrect data type",
                    text=f"Column '{col}' must contain only string values.",
                    icon="Critical"
                )
                return False

        for col in ["mz", "relative_area", "mz_window"]:
            if not pd.api.types.is_numeric_dtype(df[col]):
                UIHelpers.show_message_box(
                    self.parent,
                    title="Incorrect data type",
                    text=f"Column '{col}' may contain only numeric values.",
                    icon="Critical"
                )
                return False

        for col in ["mz", "mz_window"]:
            if (df[col] < 0).any():
                UIHelpers.show_message_box(
                    self.parent,
                    title="Negative values detected",
                    text=f"Column '{col}' contains negative values.",
                    informative_text="All numeric entries must be non-negative.",
                    icon="Critical"
                )
                return False

        # Validate that relative_area values are within the expected [0, 1] range.
        if ((df["relative_area"] < 0) | (df["relative_area"] > 1)).any():
            UIHelpers.show_message_box(
                self.parent,
                title="Invalid relative_area values",
                text="Column 'relative_area' must contain only values between 0 and 1 (inclusive).",
                informative_text=(
                    "Please check the reference file for malformed or corrupted "
                    "relative_area values and try again."
                ),
                icon="Critical"
            )
            return False
        if not pd.api.types.is_bool_dtype(df["calibrant"]):
            UIHelpers.show_message_box(
                self.parent,
                title="Incorrect data type",
                text="Column 'calibrant' must contain only boolean values (True/False).",
                icon="Critical"
            )
            return False

        # Time columns must be either both entirely filled or both entirely empty.
        time_all_null = df["time"].isnull().all()
        time_all_full = df["time"].notnull().all()
        time_window_all_null = df["time_window"].isnull().all()
        time_window_all_full = df["time_window"].notnull().all()

        if not (
            (time_all_null and time_window_all_null)
            or (time_all_full and time_window_all_full)
        ):
            UIHelpers.show_message_box(
                self.parent,
                title="Incomplete time information",
                text=(
                    "Columns 'time' and 'time_window' must be either "
                    "both completely filled or both completely empty."
                ),
                icon="Critical"
            )
            return False

        # If time columns are filled, they must be numeric and non-negative.
        if time_all_full:
            for col in ["time", "time_window"]:
                if not pd.api.types.is_numeric_dtype(df[col]):
                    UIHelpers.show_message_box(
                        self.parent,
                        title="Incorrect data type",
                        text=f"Column '{col}' may contain only numeric values.",
                        icon="Critical"
                    )
                    return False
                if (df[col] < 0).any():
                    UIHelpers.show_message_box(
                        self.parent,
                        title="Negative values detected",
                        text=f"Column '{col}' contains negative values.",
                        informative_text="All numeric entries must be non-negative.",
                        icon="Critical"
                    )
                    return False

        return True

    def _apply_ref_file(self, df: pd.DataFrame) -> None:
        """Apply a validated reference file to the application state.

        Stores the reference DataFrame, detects LC-MS vs MS-only mode,
        updates the calibration table (LC-MS only), and shows a confirmation
        pop-up to the user.

        Args:
            df: A pre-validated reference DataFrame.
        """
        self.parent.analytes_ref_df = df
        self.parent.analytes_list_df = None

        # Detect mode from time column.
        ms_only = df["time"].isnull().all()

        if ms_only:
            self.parent.set_ms_only_mode(True)
            self.ui.tableWidget_calibration.setRowCount(0)
        else:
            self.parent.set_ms_only_mode(False)
            self.parent.calibration_table_manager.update_table(df)

        UIHelpers.show_message_box(
            self.parent,
            title="Reference file detected",
            text="A reference file was successfully uploaded.",
            informative_text=(
                "The analyte reference file generation step will be "
                "skipped during batch processing."
            ),
            icon="Information"
        )

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
        # Check required columns. `mz_window`, `time`, `time_window` are optional.
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
        # Note: time and time_window are now optional (for MS-only mode).
        required_cols = [
            "analyte", "charge_min", "charge_max"
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
                    "The columns 'analyte', 'charge_min', and 'charge_max' "
                    "must be filled for all rows."
                ),
                icon="Critical"
            )
            return False
        
        # Check that time data is either completely present or completely absent.
        # Per-row check: if a row has time data, it must have both time and time_window.
        time_cols = ["time", "time_window"]
        partial_time_per_row = (
            df[time_cols].isnull().any(axis=1)
            & df[time_cols].notnull().any(axis=1)
        )
        if partial_time_per_row.any():
            UIHelpers.show_message_box(
                self.parent,
                title="Incomplete time information",
                text="Some rows have incomplete retention time data.",
                informative_text=(
                    "If a row has retention time data, both 'time' and 'time_window' "
                    "must be filled."
                ),
                icon="Critical"
            )
            return False
        
        # Global check: either ALL rows must have time data, or NO rows can have it.
        rows_with_time = df["time"].notnull().sum()
        rows_with_time_window = df["time_window"].notnull().sum()
        total_rows = len(df)
        
        # Check if we have a mix of filled and empty time data
        has_partial_data = (
            (0 < rows_with_time < total_rows) or 
            (0 < rows_with_time_window < total_rows)
        )
        
        if has_partial_data:
            UIHelpers.show_message_box(
                self.parent,
                title="Mixed time data not allowed",
                text="The analyte list contains a mix of LC-MS and MS-only data.",
                informative_text=(
                    "Either ALL rows must have retention time information (LC-MS mode), "
                    "or ALL rows must be empty (MS-only mode). "
                    "Mixing is not allowed."
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
        
        # Detect MS-only mode (all time values are NaN)
        all_time_missing = df["time"].isnull().all() and df["time_window"].isnull().all()
        
        if all_time_missing:
            # MS-only mode detected
            self.parent.set_ms_only_mode(True)
        else:
            # LC-MS mode (has retention time data)
            self.parent.set_ms_only_mode(False)
        
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
        self.parent.block_parser.update_charge_carriers()
        self.parent.block_parser.update_mass_modifiers()
    
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