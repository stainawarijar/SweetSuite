import os
import sys

import pandas as pd


# Limits for xlsx sheets
EXCEL_MAX_ROWS = 1_048_576
EXCEL_DATA_ROWS_PER_SHEET = EXCEL_MAX_ROWS - 1  # Reserve one row for headers.
EXCEL_MAX_SHEET_NAME_LENGTH = 31


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
        data_dict: dict[str, pd.DataFrame] = None
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

            if len(data) > EXCEL_DATA_ROWS_PER_SHEET:
                sheet_data = split_excel_sheet(name, data)
            else:
                sheet_data = [(name, data)]

            for sheet_name, sheet_df in sheet_data:
                sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)
                worksheet = writer.sheets[sheet_name]
                # Auto-adjust column widths.
                for i, col in enumerate(sheet_df.columns):
                    col_lens = sheet_df[col].astype(str).map(len)
                    if not col_lens.empty:
                        max_cell_len = int(col_lens.max())
                    else:
                        max_cell_len = 0
                    max_len = max(max_cell_len, len(col)) + 2  # Add some padding
                    worksheet.set_column(i, i, max_len, center_format)


def split_excel_sheet(
        sheet_name: str,
        data: pd.DataFrame
) -> list[tuple[str, pd.DataFrame]]:
    """Split a dataframe over multiple xlsx sheets if it exceeds row limits."""
    sheets = []
    row_starts = range(0, len(data), EXCEL_DATA_ROWS_PER_SHEET)
    for idx, start in enumerate(row_starts, start=1):
        suffix = str(idx)
        split_sheet_name = (
            sheet_name[:EXCEL_MAX_SHEET_NAME_LENGTH - len(suffix)] + suffix
        )
        stop = start + EXCEL_DATA_ROWS_PER_SHEET
        sheets.append((split_sheet_name, data.iloc[start:stop]))

    return sheets
