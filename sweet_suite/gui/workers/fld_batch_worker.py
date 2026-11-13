from datetime import datetime
import logging
import os
import warnings

import matplotlib
matplotlib.use("Agg")
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PyQt6.QtCore import QObject, pyqtSignal

from ... import __version__
from ...chromatography.alignment_peak import AlignmentPeak
from ...chromatography.fld_chromatogram import FldChromatogram
from ...chromatography.helpers import parse_fld_txt_file
from ...utils import utils


class FldBatchWorker(QObject):
    """Process LC-FLD files in separate alignment and quantitation passes."""

    finished = pyqtSignal(bool)
    ref_progress = pyqtSignal(int)
    alignment_progress = pyqtSignal(int)
    quantitation_progress = pyqtSignal(int)
    aborted = pyqtSignal()
    error = pyqtSignal(str, str, str, str)

    def __init__(
        self, 
        raw_folder_path: str, 
        peaks_list_df: pd.DataFrame | None,
        alignment_list_df: pd.DataFrame | None,
        alignment_time_window: float, 
        alignment_sn_cutoff: float,
        alignment_min_peaks: int, 
        quantitate_aligned_only: bool,
        parent=None,
        roi_start: float = -np.inf,
        roi_end: float = np.inf,
        peak_width: float = 1.0,
        integration_window: float = 1.0,
        correct_baseline: bool = True
    ):
        super().__init__(parent)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info(f"\nFldBatchWorker initialized at {self.start_time}")
        self.raw_folder_path = raw_folder_path
        self.peaks_list_df = peaks_list_df
        self.alignment_list_df = alignment_list_df
        self.alignment_time_window = alignment_time_window
        self.alignment_sn_cutoff = alignment_sn_cutoff
        self.alignment_min_peaks = alignment_min_peaks
        self.quantitate_aligned_only = quantitate_aligned_only
        self.roi_start = roi_start
        self.roi_end = roi_end
        self.peak_width = peak_width
        self.integration_window = integration_window
        self.correct_baseline = correct_baseline
        self.start_time = datetime.now().strftime("%d-%m-%Y_%H%M%S")
        self.excel_path = self.get_output_excel_path()
        self.stop_requested = False

    def get_output_excel_path(self) -> str | None:
        """Set path to Excel file to which final results will be written.
        
        Returns:
            The path as a string, or None if the raw folder path does
            not exist (possible when only an analytes list is uploaded).
        """
        if self.raw_folder_path is None:
            return

        return os.path.join(
            self.raw_folder_path,
            f"{self.start_time}_SweetSuite_results.xlsx"
        )

    def stop(self) -> None:
        """Request the worker to stop processing."""
        self.logger.info("FldBatchWorker stop requested by user")
        self.stop_requested = True

    def run(self) -> None:
        """Main execution method for batch processing."""
        self.logger.info("FldBatchWorker run started")

        # Check the raw-data directory before processing.
        if self.raw_folder_path is None:
            self.logger.warning("Missing batch directory")
            self.error.emit(
                "Missing batch directory",
                "Select a folder containing raw data files.",
                "",
                "Warning"
            )
            self.finished.emit(False)
            return

        # Retention time alignment.
        if self.alignment_list_df is None:
            aligned_finished = None
        else:
            try:
                # Collect all .txt file paths
                txt_file_paths = self.get_txt_file_paths()

                # Check if there actually are files.
                if len(txt_file_paths) == 0:
                    self.logger.warning(
                        "Batch directory contained no text files"
                    )
                    self.error.emit(
                        "Empty directory",
                        "The specified folder contains no txt files.",
                        "",
                        "Warning"
                    )
                    self.finished.emit(False)
                    return

                self.logger.info(
                    f"Found {len(txt_file_paths)} text files for alignment."
                )

                # Read in the data from the files and perform alignment.
                aligned_finised = self.align_txt_files(txt_file_paths)
                if not aligned_finised[0]:
                    # Batch process was aborted
                    return

            except Exception as exc:
                self.logger.exception(
                    "Unexpected error during alignment: "
                    f"{str(exc)}"
                )
                self.error.emit(
                    "Processing error",
                    "Unexpected error during alignment:",
                    str(exc),
                    "Critical"
                )
                self.finished.emit(False)
                return

            # TODO: Message with number of files for which error occured

            
    def get_txt_file_paths(self) -> list[str]:
        """Collect all txt file paths from the specified folder."""
        txt_file_paths = []
        for file in os.listdir(self.raw_folder_path):
            if file.endswith(".txt"):
                full_path = os.path.join(self.raw_folder_path, file)
                txt_file_paths.append(full_path)

        return txt_file_paths

    def align_txt_files(self, txt_file_paths: list[str]) -> tuple[bool, int]:
        """Perform retention time alignment on raw chromatogram data.
        
        Args:
            txt_file_paths: ...
        
        Returns:
            A tuple `(finished, errors)` where `finished` is a boolean indicating
            whether the alignment process finished, and `errors` indicates the
            number of files for which an unexpected error occured.
        """
        # Create a list with alignment peaks.
        alignment_peaks = sorted([
            AlignmentPeak(
                peak=str(row["peak"]),
                time_required = float(row["time"]),
                alignment_time_window=(
                    self.alignment_time_window if pd.isnull(row["time_window"])
                    else float(row["time_window"])
                ),
                alignment_sn_cutoff = (
                    self.alignment_sn_cutoff if pd.isnull(row["sn_cutoff"])
                    else float(row["sn_cutoff"])
                ),
                required = not pd.isnull(row["required"])
            ) for _, row in self.alignment_list_df.iterrows()
        ], key=lambda feature: feature.time_required)

        # Set path to pdf with figures.
        pdf_path = os.path.join(
            self.raw_folder_path,
            f"{self.start_time}_alignment.pdf"
        )

        # Loop over text file paths, keeping track of processed files and errors.
        n = len(txt_file_paths)
        errors = 0
        with PdfPages(pdf_path) as pdf:
            for idx, path in enumerate(txt_file_paths):
                # Check if stop was requested.
                if self.stop_requested:
                    self.logger.info("FldBatchWorker stop requested during alignment")
                    self.aborted.emit()
                    return (False, errors)

                # Attempt to create an `FldChromatogram` instance.
                try:
                    chrom = FldChromatogram(
                        data=parse_fld_txt_file(path),
                        start_time=self.start_time,
                        end_time=self.end_time,
                        peak_width=self.peak_width,
                        alignment_peaks=alignment_peaks
                    )
                except Exception as exc:
                    self.logger.error(
                        f"Unexpected error in reading {path}: {str(exc)}"
                    )
                    self.logger.info("Continuing with next file")
                    errors += 1
                    continue

                # Perform baseline correction.
                if self.correct_baseline:
                    try:
                        chrom.correct_baseline()
                    except Exception as exc:
                        self.logger.error(
                            f"Unexpected error while attempting baseline correction for {path}: {str(exc)}"
                        )
                        self.logger.info("Continuing with next file")
                        errors += 1
                        continue

                # TODO: Alignment here...

                # Update percentage of processed files
                percent = round((idx + 1) / n * 100)
                self.alignment_progress.emit(percent)

            return (True, errors)
                








            
            


            
            

    
