from datetime import datetime
import logging
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PyQt6.QtCore import QObject, pyqtSignal

from ... import __version__
from ...chromatography.alignment_peak import AlignmentPeak
from ...chromatography.fld_chromatogram import FldChromatogram
from ...chromatography.helpers import parse_fld_txt_file


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
        self.start_time = datetime.now().strftime("%d-%m-%Y_%H%M%S")
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

        elif len(self.alignment_list_df) < self.alignment_min_peaks:
            self.logger.error("Not enough alignment peaks specified")
            self.error.emit(
                "Specify more alignment peaks specified",
                "The provided alignment list does not contain enough peaks.",
                f"{len(self.alignment_list_df)} peaks are specified, but at least {self.alignment_min_peaks} are required.",
                "Warning"
            )
            self.finished.emit(False)
            return
        
        else:
            try:
                # Collect all .txt file paths
                txt_file_paths = self.get_txt_file_paths(subset="raw")

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
                aligned_finished = self.align_txt_files(txt_file_paths)

                if not aligned_finished:
                    return  # Batch process was aborted

            except Exception as exc:
                self.logger.exception(
                    "Unexpected error during alignment: "
                    f"{str(exc)}"
                )
                self.error.emit(
                    "Processing error",
                    "Unexpected error during alignment: ",
                    str(exc),
                    "Critical"
                )
                self.finished.emit(False)
                return
        
        # Check if stop was requested before continuing.
        if self.stop_requested:
            self.logger.info(
                "FldBatchWorker aborted after alignment"
            )
            self.aborted.emit()
            return

        # TODO: Quantitation
        if self.peaks_list_df is None:
            quantitation_results = None
        else:
            try:
                print("Quantitation code where are you?")
                # NOTE None-aligned file: assume Thermo format
                # NOTE Aligned file: assume simple tab-separated txt format
                quantitation_results = self.quantify()  # Returns False for now.

                # Check if batch processing was aborted during quantitation.
                if not quantitation_results:
                    return

            except Exception as exc:
                self.logger.exception(
                    "Unexpected error during quantitation: ",
                    f"{str(exc)}"
                )
                self.error.emit(
                    "Processing error",
                    "Unexpected error during quantitation:",
                    str(exc),
                    "Critical"
                )
                self.finished.emit(False)
                return

        # NOTE Temporary finished emit
        # TODO Remove
        self.logger.info("FldBatchWorker alignment finished")
        self.finished.emit(True)

        # TODO: Export results
        # try:
        #     self.export_results(
        #         aligned=(
        #             aligned_finished if aligned_finished is not None
        #             else False
        #         ),
        #         quantitation_results=quantitation_results
        #     )
        #     self.logger.info("FldBatchWorker finished successfully")
        #     self.finished.emit(True)
        # except Exception as exc:
        #     self.logger.exception(
        #         "Unexpected error while exporting results: "
        #         f"{str(exc)}"
        #     )
        #     self.error.emit(
        #         "Processing error",
        #         "Unexpected error while exporting results:",
        #         str(exc),
        #         "Critical"
        #     )
        #     self.finished.emit(False)
        #     return

    def get_txt_file_paths(
        self,
        subset: str = "all"
    ) -> list[str]:
        """Collect all txt file paths from the specified folder, with the option
        to only return files with or without an 'aligned' prefix. 
        
        Files with an 'unaligned' prefix, i.e. files for which alignment failed, 
        are never returned.

        Args:
            subset: One of `'all'`, `'raw'` and `'aligned'`, with `'all'` being
                the default. When using `'raw'`, only files without an 'aligned'
                prefix are returned. When using `'aligned'`, only files with
                an 'aligned' prefix are returned.
        """
        txt_file_paths = []

        if subset == "all":
            for file in os.listdir(self.raw_folder_path):
                if file.endswith(".txt"):
                    if file.startswith("unaligned"):
                        continue
                    full_path = os.path.join(self.raw_folder_path, file)
                    txt_file_paths.append(full_path)

        elif subset == "raw":
            for file in os.listdir(self.raw_folder_path):
                if file.endswith(".txt") and not file.startswith("aligned"):
                    if file.startswith("unaligned"):
                        continue
                    full_path = os.path.join(self.raw_folder_path, file)
                    txt_file_paths.append(full_path)

        elif subset == "aligned":
            for file in os.listdir(self.raw_folder_path):
                if file.endswith(".txt") and file.startswith("aligned"):
                    full_path = os.path.join(self.raw_folder_path, file)
                    txt_file_paths.append(full_path)

        return txt_file_paths

    def align_txt_files(
        self, 
        txt_file_paths: list[str]
    ) -> bool:
        """Perform retention time alignment on raw chromatogram data.
        
        Args:
            txt_file_paths: A list containing paths to the chromatogram
                text files.
        
        Returns:
            `True` if the alignment batch process finished, `False` if it was
            aborted.
        """
        # Create a list with alignment peaks.
        alignment_peaks = sorted([
            AlignmentPeak(
                peak=str(row["peak"]),
                time_required = float(row["time"]),
                time_window=(
                    self.alignment_time_window if pd.isnull(row["time_window"])
                    else float(row["time_window"])
                ),
                sn_cutoff = (
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

        # Loop over file paths, keeping track of processed files and errors.
        n = len(txt_file_paths)
        with PdfPages(pdf_path) as pdf:
            for idx, path in enumerate(txt_file_paths):
                # Check if stop was requested.
                if self.stop_requested:
                    self.logger.info("FldBatchWorker stop requested during alignment")
                    self.aborted.emit()
                    return False

                # Create an `FldChromatogram` instance.
                chrom = FldChromatogram(
                    name=os.path.basename(path),
                    data=parse_fld_txt_file(path),
                    start_time=self.roi_start,
                    end_time=self.roi_end,
                    peak_width=self.peak_width,
                    alignment_peaks=alignment_peaks
                )

                # Perform baseline correction if applicable.
                if self.correct_baseline:
                    chrom.correct_baseline()

                # Create alignment fit.
                fit = chrom.get_alignment_fit(
                    min_peaks=self.alignment_min_peaks
                )
                poly, fig = fit[0], fit[1]

                if poly is not None:
                    try:
                        # Apply polynomial fit to get aligned data.
                        data_aligned = chrom.get_aligned_data(poly=poly)

                        # Write aligned data to a tab-separated text file.
                        np.savetxt(
                            Path(path).with_name(f"aligned-{Path(path).name}"),
                            data_aligned,
                            delimiter="\t", fmt="%.8f"
                        )

                        pdf.savefig(fig)
                        self.logger.info(
                            f"Alignment fit successful for {os.path.basename(path)}"
                        )
                    finally:
                        plt.close(fig)

                else:
                    np.savetxt(
                        Path(path).with_name(f"unaligned-{Path(path).name}"),
                        np.empty(shape=0)
                    )
                    self.logger.info(
                        f"Alignment fit failed for {os.path.basename(path)}"
                    )

                percentage = round((idx + 1) / n * 100)
                self.alignment_progress.emit(percentage)

            return True

    def quantify(
        self
    ) -> bool:
        """
        """
        # TODO: Quantitation
        return False
