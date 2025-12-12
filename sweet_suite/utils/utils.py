import os
import sys

import pandas as pd


def format_execution_time(
        start_time: float,
        end_time: float
) -> str:
    """Return a human-readable elapsed time between two timestamps.

    Args:
        start_time: Start timestamp in seconds.
        end_time: End timestamp in seconds.

    Returns:
        Nicely formatted string displaying the amount of hours, minutes
        and seconds.
    """
    elapsed = abs(end_time - start_time)  # Seconds
    h = int(elapsed // 3600)  # Hours
    m = int((elapsed % 3600) // 60)  # Minutes
    s =  int(elapsed % 60)  # Remaining seconds

    return f"Execution time: {h} hours, {m} minutes and {s} seconds."


def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    
    return os.path.join(os.path.abspath("."), relative_path)


def write_to_excel(
        out_path: str,
        data_dict: dict[pd.DataFrame] = None
) -> None:
    """Writes dataframes to an Excel file, and sets the widths of
    the columns for readability.

    Args:
        out_path: Path to which the data should be written.
        data_dict: A dictionary containing dataframes to be written to 
            the Excel file. Each dataframe will be written to a separate
            sheet, named after the corresponding key.
    """
    with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
        center_format = writer.book.add_format({'align': 'center'})  
        for name, data in data_dict.items():
            if data is None:
                continue
            data.to_excel(writer, sheet_name=name, index=False)
            worksheet = writer.sheets[name]
            # Auto-adjust column widths.
            for i, col in enumerate(data.columns):
                max_len = max(
                    data[col].astype(str).map(len).max(),
                    len(col)  # Include header length
                ) + 2  # Add some padding
                worksheet.set_column(i, i, max_len, center_format)
