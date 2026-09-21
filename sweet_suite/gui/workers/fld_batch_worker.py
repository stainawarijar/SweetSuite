"""Worker scaffold for the future LC-FLD batch processing pipeline."""

import logging
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal


class FldBatchWorker(QObject):
    """Store FLD settings and provide the coordinator's worker interface.

    Raw-data loading, alignment, integration and export are not implemented yet.
    The scaffold reports this explicitly and never reports successful analysis.
    """

    finished = pyqtSignal(bool)
    ref_progress = pyqtSignal(int)
    alignment_progress = pyqtSignal(int)
    quantitation_progress = pyqtSignal(int)
    aborted = pyqtSignal()
    error = pyqtSignal(str, str, str, str)

    def __init__(
        self, 
        raw_folder_path: str, 
        peaks_list_path: str | None,
        alignment_list_path: str | None,
        alignment_time_window: float, 
        alignment_sn_cutoff: float,
        alignment_min_peaks: int, 
        quantitate_aligned_only: bool,
        parent=None
    ):
        super().__init__(parent)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.raw_folder_path = raw_folder_path
        self.peaks_list_path = peaks_list_path
        self.alignment_list_path = alignment_list_path
        self.alignment_time_window = alignment_time_window
        self.alignment_sn_cutoff = alignment_sn_cutoff
        self.alignment_min_peaks = alignment_min_peaks
        self.quantitate_aligned_only = quantitate_aligned_only
        self.stop_requested = False

    def stop(self) -> None:
        """Request cancellation before the next processing step."""
        self.stop_requested = True

    def run(self) -> None:
        # TODO: Batch processing steps (see MsBatchWorker)

        if not Path(self.raw_folder_path).is_dir():
            self.error.emit(
                "Missing batch directory", 
                "The specified folder does not exist.",
                self.raw_folder_path, 
                "Warning"
            )
        else:
            self.error.emit(
                "LC-FLD processing",
                "LC-FLD batch processing is not implemented yet.",
                "No data were processed or exported.", 
                "Information"
            )
        self.finished.emit(False)
