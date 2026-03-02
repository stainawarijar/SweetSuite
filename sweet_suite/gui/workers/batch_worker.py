from datetime import datetime
import logging
import os
import warnings

import matplotlib
matplotlib.use("Agg")
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PyQt6.QtCore import QObject, pyqtSignal

from ... import __version__
from ...chromatography.alignment_feature import AlignmentFeature
from ...input_analyte import InputAnalyte
from ...reporting import ms_tables
from ...mass_spectrometry.mass_spectrum import MassSpectrum
from ...mzxml import Mzxml
from ...utils import utils


class BatchWorker(QObject):
    """
    PyQt6 worker for batch processing mass spectrometry data in SweetSuite.

    Handles complete workflow:
    - Analytes reference file generation.
    - Chromatogram alignment across mzXML files.
    - Analyte quantitation with calibration and background correction.
    - Excel export with metadata.

    Runs in separate thread for GUI responsiveness.
    Emits progress signals and can be stopped via stop() method.
    """

    finished = pyqtSignal(bool)
    ref_progress = pyqtSignal(int)
    alignment_progress = pyqtSignal(int)
    quantitation_progress = pyqtSignal(int)
    aborted = pyqtSignal()
    error = pyqtSignal(str, str, str, str)  # title, text, informative, icon

    def __init__(
            self,
            blocks: dict[dict],
            raw_folder_path: str | None,
            ms_only: bool,
            alignment_list_df: pd.DataFrame | None,
            alignment_time_window: float,
            alignment_mz_window: float,
            alignment_sn_cutoff: float,
            alignment_min_peaks: int,
            analytes_list_df: pd.DataFrame | None,
            analytes_ref_df: pd.DataFrame | None,
            sum_spectra_calibration: dict,
            charge_carrier: str,
            sum_spectrum_resolution: int,
            background_mass_window: float,
            calibration_mass_window: float,
            calibrant_sn_cutoff: float,  # Global value
            quantitation_mz_window: float,
            min_calibrant_number: int,
            min_isotopic_fraction: float,
            quantitate_aligned_only: bool,
            quadratic_mz_window: bool,
            quadratic_coeffs: tuple[float, float, float],
            mass_modifier: str | None = None,
            use_peak_height: bool = False,
            parent = None
    ):
        super().__init__(parent)
        self.start_time = datetime.now().strftime("%d-%m-%Y_%H%M")
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info(f"\nBatchWorker initialized at {self.start_time}")
        self.blocks = blocks
        self.raw_folder_path = raw_folder_path
        self.ms_only = ms_only
        self.alignment_list_df = alignment_list_df
        self.alignment_time_window = alignment_time_window
        self.alignment_mz_window = alignment_mz_window
        self.alignment_sn_cutoff = alignment_sn_cutoff
        self.alignment_min_peaks = alignment_min_peaks
        self.analytes_list_df = analytes_list_df
        self.analytes_ref_df = analytes_ref_df
        self.sum_spectra_calibration = sum_spectra_calibration
        self.charge_carrier = charge_carrier
        self.mass_modifier = mass_modifier
        self.sum_spectrum_resolution = sum_spectrum_resolution
        self.background_mass_window = background_mass_window
        self.calibration_mass_window = calibration_mass_window
        self.calibrant_sn_cutoff = calibrant_sn_cutoff
        self.quantitation_mz_window = quantitation_mz_window
        self.min_calibrant_number = min_calibrant_number
        self.min_isotopic_fraction = min_isotopic_fraction
        self.quantitate_aligned_only = quantitate_aligned_only
        self.quadratic_mz_window = quadratic_mz_window
        self.quadratic_coeffs = quadratic_coeffs
        self.use_peak_height = use_peak_height
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

        excel_path = os.path.join(
            self.raw_folder_path,
            f"{self.start_time}_SweetSuite_results.xlsx"
        )

        return excel_path

    def stop(self) -> None:
        """Request the worker to stop processing."""
        self.logger.info("BatchWorker stop requested by user")
        self.stop_requested = True
    
    def run(self) -> None:
        """Main execution method for batch processing."""
        self.logger.info("BatchWorker run started")
        # Generate analytes reference file if applicable.
        if self.analytes_list_df is None and self.analytes_ref_df is None:
            self.logger.info(
                "No analytes provided, skipping reference file generation"
            )
            analytes_ref_path = None

        elif self.analytes_ref_df is not None:
            # Reference file was uploaded directly: write it to disk and skip
            # the generation step.
            self.logger.info("Using pre-loaded analytes reference file")
            try:
                analytes_ref_path = self.write_ref_df(self.analytes_ref_df)
                self.logger.info(
                    f"Pre-loaded reference file written to: {analytes_ref_path}"
                )
            except Exception as e:
                self.logger.exception(
                    f"Error writing pre-loaded reference file: {str(e)}"
                )
                self.error.emit(
                    "Error",
                    "Could not write the reference file to disk:",
                    str(e),
                    "Critical"
                )
                self.finished.emit(False)
                return
            self.ref_progress.emit(100)

        else:
            try:
                # Write analytes reference file to batch folder,
                # or to current directory if none was selected.
                self.logger.info("Generating analytes reference file")
                analytes_ref_path = self.make_ref_file()
                self.logger.info(f"Reference file created at: {analytes_ref_path}")
            
            except KeyError as e:
                self.logger.error(f"Unknown charge carrier block: {str(e)}")
                self.error.emit(
                    "Unknown charge carrier block",
                    f"The block file {str(e)} could not be found.",
                    "",
                    "Critical"
                )
                self.finished.emit(False)
                return
            
            except OSError:
                self.logger.error(f"Batch directory missing: {str(e)}")
                self.error.emit(
                    "Non-existing directory",
                    "The specified batch directory could not be found.",
                    "",
                    "Critical"
                )
                self.finished.emit(False)
                return
            
            except Exception as e:
                self.logger.exception(
                    "Unexpected error while creating analytes reference file: "
                    f"{str(e)}"
                )
                self.error.emit(
                    "Error",
                    "Unexpected error while creating analytes reference file:",
                    str(e),
                    "Critical"
                )
                self.finished.emit(False)
                return

        # Check if stopped before continuing.
        if self.stop_requested:
            self.logger.info(
                "BatchWorker aborted after generation of reference file"
            )
            self.aborted.emit()
            return
        
        # Check if the mzXML folder path is missing.
        if self.raw_folder_path is None:
            if analytes_ref_path is None:
                message = ""
            else:
                message = f"Analytes reference file was created at {analytes_ref_path}"
            self.logger.warning("No batch directory selected")
            self.error.emit(
                    "Missing batch directory",
                    "Select a folder containing raw data files.",
                    message,
                    "Warning"
                )
            self.finished.emit(False)
            return

        # Retention time alignment.
        # Skip alignment entirely if in MS-only mode.
        if self.ms_only:
            self.logger.info("MS-only mode: skipping alignment")
            aligned_finished = None
        elif self.alignment_list_df is None:
            aligned_finished = None
        else:
            try:
                # Collect all mzXML file paths.
                mzxml_file_paths = self.get_mzxml_file_paths()
                self.logger.info(
                    f"Found {len(mzxml_file_paths)} mzXML files for alignment"
                )

                # Check if folder actually contained files.
                if len(mzxml_file_paths) == 0:
                    self.logger.warning(
                        "Batch directory contained no mzXML files"
                    )
                    self.error.emit(
                        "Empty directory",
                        "The specified folder contains no mzMXL files.",
                        "",
                        "Warning"
                    )
                    self.finished.emit(False)
                    return
                
                # Align the mzXML files.
                # When False is returned, batch process was aborted.
                aligned_finished = self.align_mzxml_files(mzxml_file_paths)
                if not aligned_finished: 
                    return

            except Exception as e:
                self.logger.exception(
                    "Unexpected error during alignment: "
                    f"{str(e)}"
                )
                self.error.emit(
                    "Processing error",
                    "Unexpected error during alignment:",
                    str(e),
                    "Critical"
                )
                self.finished.emit(False)
                return
        
        # Check if stopped before continuing.
        if self.stop_requested:
            self.logger.info("BatchWorker aborted after alignment")
            self.aborted.emit()
            return
        
        # Calibration and quantitation.
        if analytes_ref_path is None:
            quantitation_results = None
        else:
            try:
                if self.ms_only:
                    # MS-only mode: process xy files
                    xy_file_paths = self.get_xy_file_paths()

                    # Check if folder actually contained xy files.
                    if len(xy_file_paths) == 0:
                        self.logger.warning(
                            "Batch directory contained no .xy files"
                        )
                        self.error.emit(
                            "Empty directory",
                            "The specified folder contains no .xy files.",
                            "",
                            "Warning"
                        )
                        self.finished.emit(False)
                        return

                    self.logger.info(
                        f"Starting quantitation of {len(xy_file_paths)} .xy files"
                    )
                    quantitation_results = self.quantitate_xy_files(
                        analytes_ref_path, xy_file_paths
                    )
                else:
                    # LC-MS mode: process mzXML files
                    # Create new list with mzXML file paths.
                    mzxml_file_paths = self.get_mzxml_file_paths()

                    # Check if folder actually contained files.
                    if len(mzxml_file_paths) == 0:
                        self.logger.warning(
                            "Batch directory contained no mzXML files"
                        )
                        self.error.emit(
                            "Empty directory",
                            "The specified folder contains no mzXML files.",
                            "",
                            "Warning"
                        )
                        self.finished.emit(False)
                        return

                    if not self.quantitate_aligned_only:
                        self.logger.info(
                            f"Starting quantitation of {len(mzxml_file_paths)}"
                            " mzXML files"
                        )
                        quantitation_results = self.quantitate_mzxml_files(
                            analytes_ref_path, mzxml_file_paths
                        )
                    else:
                        aligned_mzxml_file_paths = [
                            path for path in mzxml_file_paths
                            if os.path.basename(path).startswith("aligned")
                        ]
                        if len(aligned_mzxml_file_paths) > 0:
                            self.logger.info(
                                f"Starting quantitation of {len(aligned_mzxml_file_paths)}"
                                " aligned mzXML files"
                            )
                            quantitation_results = self.quantitate_mzxml_files(
                                analytes_ref_path, aligned_mzxml_file_paths
                            )
                        else:
                            self.logger.warning("No aligned files found for quantitation")
                            self.error.emit(
                                "No aligned files",
                                "No aligned files were detected for quantitation.",
                                "",
                                "Warning"
                            )
                            self.finished.emit(False)
                            return
                
                # Check if batch processing was aborted during quantitation.
                if quantitation_results is None:
                    return

            except Exception as e:
                self.logger.exception(
                    "Unexpected error during quantitation: "
                    f"{str(e)}"
                )
                self.error.emit(
                    "Processing error",
                    "Unexpected error during quantitation:",
                    str(e),
                    "Critical"
                )
                self.finished.emit(False)
                return
            
        self.export_results(
            aligned=(
                aligned_finished if aligned_finished is not None
                else False
            ),
            quantitation_results=quantitation_results
        )
        self.logger.info("BatchWorker finished successfully")
        self.finished.emit(True)
    
    def write_ref_df(self, ref_df: pd.DataFrame) -> str:
        """Write a pre-loaded reference DataFrame to disk as an .xlsx file.

        Args:
            ref_df: Reference DataFrame in the standard reference file format.

        Returns:
            Absolute path to the written .xlsx file.
        """
        out_dir = (
            os.getcwd() if self.raw_folder_path is None
            else self.raw_folder_path
        )
        out_path = os.path.join(
            out_dir,
            f"{self.start_time}_analytes_ref.xlsx"
        )
        utils.write_to_excel(out_path, {"analytes": ref_df})
        return out_path

    def make_ref_file(self) -> str:
        """Generate the analytes reference .xlsx file and return its path."""
        raw_folder_path=(
            os.getcwd() if self.raw_folder_path is None
            else self.raw_folder_path
        )
        # Keep track of percentage.
        n = len(list(self.analytes_list_df.itertuples()))
        percentage = 0

        # Initiate empty reference DataFrame.
        reference = pd.DataFrame()

        # Check if m/z window is constant or quadratic function of m/z.
        if self.quadratic_mz_window:
            mz_window_coeffs = self.quadratic_coeffs  # (a, b, c)
        else:
            mz_window_coeffs = (float(0), float(0), self.quantitation_mz_window)

        for idx, line in enumerate(list(self.analytes_list_df.itertuples())):
            # Handle time data based on mode (MS-only vs LC-MS)
            if self.ms_only:
                # MS-only mode: time and time_window should be None
                time_val = None
                time_window_val = None
            else:
                # LC-MS mode: convert to float
                time_val = float(line.time)
                time_window_val = float(line.time_window)
            
            # Create instance of InputAnalyte.
            input_analyte = InputAnalyte(
                blocks = self.blocks,
                name=str(line.analyte),
                charge_min=int(line.charge_min),
                charge_max=int(line.charge_max),
                mz_window_coeffs=(
                    mz_window_coeffs if pd.isnull(line.mz_window)
                    else (float(0), float(0), float(line.mz_window))
                ),
                time=time_val,
                time_window=time_window_val,
                calibrant=(not pd.isnull(line.calibrant)),
                min_isotopic_fraction=self.min_isotopic_fraction,
                charge_carrier=self.charge_carrier,
                mass_modifier=self.mass_modifier
            )

            # Append to larger reference data frame.
            if reference.empty:
                reference = input_analyte.reference_df
            else:
                reference = pd.concat(
                    [reference, input_analyte.reference_df],
                    ignore_index = True
                )
            
            # Update percentage and report callback.
            percentage = round((idx + 1) / n * 100)
            self.ref_progress.emit(percentage)
            
        # Write reference data frame to Excel file.
        out_path = os.path.join(
            raw_folder_path,
            f"{self.start_time}_analytes_ref.xlsx"
        )
        utils.write_to_excel(out_path, {"analytes": reference})

        return out_path
    
    def get_mzxml_file_paths(self) -> list[str]:
        """Collect all mzXML file paths from the specified folder."""
        mzxml_file_paths = []
        for file in os.listdir(self.raw_folder_path):
            if file.endswith(".mzXML"):
                full_path = os.path.join(self.raw_folder_path, file)
                mzxml_file_paths.append(full_path)
        
        return mzxml_file_paths
    
    def get_xy_file_paths(self) -> list[str]:
        """Collect all .xy file paths from the specified folder."""
        xy_file_paths = []
        for file in os.listdir(self.raw_folder_path):
            if file.endswith(".xy"):
                full_path = os.path.join(self.raw_folder_path, file)
                xy_file_paths.append(full_path)
        
        return xy_file_paths
    
    def read_xy_file(self, file_path: str) -> np.ndarray:
        """Read an xy file and return as a 2D numpy array.

        If the intensity column contains negative values, all intensities are
        shifted upward by the absolute value of the minimum so that the lowest
        intensity becomes zero.
        
        Args:
            file_path: Path to the .xy file.
        
        Returns:
            2D numpy array with m/z values in first column and 
            intensities in second column.
        """
        try:
            # Read the xy file as space or tab-delimited data
            # Suppress the UserWarning numpy emits for empty files; we handle
            # that case ourselves via the size check below.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                data = np.loadtxt(file_path)
        except Exception as e:
            self.logger.error(f"Error reading xy file {file_path}: {str(e)}")
            raise

        # Validate shape outside the try/except so that ValueError propagates
        # to the caller without being logged as an error here.
        if data.size == 0:
            raise ValueError(f"Expected 2 columns, got 0")

        # Ensure it's 2D with shape (n, 2)
        if data.ndim == 1:
            # If 1D, reshape to (1, 2) assuming single data point
            data = data.reshape(1, -1)

        if data.shape[1] != 2:
            raise ValueError(f"Expected 2 columns, got {data.shape[1]}")

        # Shift intensities so the minimum is zero if any are negative.
        min_intensity = data[:, 1].min()
        if min_intensity < 0:
            data[:, 1] -= min_intensity
            self.logger.info(
                f"Negative intensities detected in {os.path.basename(file_path)}: "
                f"shifted all intensities by {-min_intensity:.6g} to baseline zero"
            )

        return data

    def align_mzxml_files(self, mzxml_file_paths: list[str]) -> bool:
        """Align retention times of mzXML files in batch process.
        
        Args:
            mzxml_file_paths: List of paths to mzXML files to align.
        
        Returns:
            True if alignment finished. False if alignment was aborted.
        """
        # Create a list with alignment features.
        alignment_features = sorted([
            AlignmentFeature(
                mz_exact = float(row["mz"]),
                time_required = float(row["time"]),
                alignment_time_window = (
                    self.alignment_time_window if pd.isnull(row["time_window"])
                    else float(row["time_window"])
                ),
                alignment_mz_window = (
                    self.alignment_mz_window if pd.isnull(row["mz_window"])
                    else float(row["mz_window"])
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

        # Loop over mzXML file paths, keeping track of processed files.
        n = len(mzxml_file_paths)
        with PdfPages(pdf_path) as pdf:
            for idx, path in enumerate(mzxml_file_paths):
                # Check if stop was requested.
                if self.stop_requested:
                    self.logger.info("BatchWorker stop requested during alignment")
                    self.aborted.emit()
                    return False

                # Read mzXML file and make alignment fit.
                mzxml = Mzxml(path)
                if len(mzxml.times_bytes) == 0:
                    self.logger.warning(
                        f"Alignment skipped for empty file {os.path.basename(path)}"
                    )
                    continue

                fit_eics = mzxml.get_alignment_fit_eics(
                    alignment_features=alignment_features,
                    min_peaks=self.alignment_min_peaks
                )

                # Create figure.
                plot = mzxml.plot_alignment_fit(fit_eics)
                if plot is not None:
                    self.logger.info(
                        f"Alignment fit succesful for {os.path.basename(path)}"
                    )
                    pdf.savefig(plot)
                    plt.close(plot)
                    # Set plot to None to free up memory.
                    plot = None
                else:
                    self.logger.info(
                        f"Alignment fit failed for {os.path.basename(path)}"
                    )

                # Adjust retention times of the mzXML file.
                mzxml.align_retention_times(fit_eics)

                # Update percentage of processed files.
                percent = round((idx + 1) / n * 100)
                self.alignment_progress.emit(percent)
        
        return True
    
    def quantitate_mzxml_files(
            self,
            analytes_ref_path: str,
            mzxml_file_paths: list[str]
    ) -> pd.DataFrame | None:
        """
        Perform calibration and quantitation on the mzXML files.

        Args:
            analytes_ref_path: Path to the analytes reference Excel file.
            mzxml_file_paths: List of paths to mzXML files.
        
        Returns:
            Dataframe with quantitation results if processing finished for
            all files. None if batch process was aborted during quantitation.
        """
        # Get distinct retention times ranges as a list of tuples.
        rt_ranges = list(self.sum_spectra_calibration.keys())

        # Read in analytes reference Excel file.
        # Then extract the data for the calibrants.
        analytes_ref = pd.read_excel(analytes_ref_path)
        ref_calibrants = analytes_ref[analytes_ref["calibrant"]]

        # Create a list with required output parameters.
        output_params = [
            "total_area_background_subtracted",
            "mass_error_ppm",
            "isotopic_pattern_quality",
            "signal_to_noise",
            "total_area",
            "total_background",
            "total_noise"
        ]

        # Set path to pdf file with calibration figures.
        pdf_path = os.path.join(
            self.raw_folder_path,
            f"{self.start_time}_calibration.pdf"
        )

        # Set path to temporary CSV file for accumulating results.
        # (Faster than writing to dataframes one-by-one to Excel).
        temp_csv_path = os.path.join(
            self.raw_folder_path,
            f"{self.start_time}_temp_results.csv"
        )
        # Delete existing CSV file if it exists.
        if os.path.exists(temp_csv_path):
            self.logger.info("Removing existing temporary results file")
            os.remove(temp_csv_path)
        # Ensure the temp CSV starts fresh.
        with open(temp_csv_path, "w", newline="") as f:
            pass

        # Loop over mzXML file paths and create mass spectra.
        # Keep track of number of processed files.
        n = len(mzxml_file_paths)
        header = True  # Set to `false` after first non-empty mzXML file is processed.
        with PdfPages(pdf_path) as pdf:
            for idx, path in enumerate(mzxml_file_paths):

                # Check if stop was requested.
                if self.stop_requested:
                    self.logger.info("BatchWorker stop requested during quantitation")
                    self.aborted.emit()
                    return

                # Read mzXML file.
                mzxml = Mzxml(path)

                # If the mzXML file is empty, continue with next file.
                if mzxml.retention_times.size == 0:
                    self.logger.warning(
                        f"{mzxml.file_name}.mzXML contains no data. " 
                        "Continuing with the next file." 
                    )
                    percent = round((idx + 1) / n * 100)
                    self.quantitation_progress.emit(percent)
                    continue

                # List to collect `MassSpectrum` instances.
                mass_spectra = []
                
                # Create sum spectrum for each retention time range.
                for pair in rt_ranges:
                    sum_spectrum = mzxml.create_sum_spectrum(
                        time=float(pair[0]),
                        time_window=float(pair[1]),
                        resolution=self.sum_spectrum_resolution
                    )

                    # Check for calibration.
                    if not self.sum_spectra_calibration[pair]["calibrate"]:
                        # No calibration -> empty list.
                        calibrants_list = []
                        # Set calibration S/N cut-off to None.
                        calibration_sn_cutoff = None
                    else:
                        # Select calibrants in this retention time range.
                        calibrants_df = (
                            ref_calibrants[
                                (ref_calibrants["time"] == sum_spectrum.time) &
                                (ref_calibrants["time_window"] == sum_spectrum.time_window)
                            ]
                            .assign(
                                # Extract charge number from peak name.
                                charge = lambda x: (
                                    x["peak"].str.split("_").str[1].astype(int)
                                )
                            )
                            # Select required columns.
                            [["mz", "charge", "mz_window"]]
                        )

                        # Create a list with (m/z, charge, m/z window) tuples.
                        calibrants_list = list(calibrants_df.itertuples(
                            index=False, name=None
                        ))

                        # Determine calibration S/N cut-off.
                        calibration_sn_cutoff = float(
                            self.sum_spectra_calibration[pair]["sn_cutoff"]
                        )
                
                    # Create an instance of MassSpectrum.
                    mass_spectrum = MassSpectrum(
                        name=sum_spectrum.name,
                        file_raw=sum_spectrum.file_raw,
                        data_uncalibrated=sum_spectrum.data,
                        background_mass_window=self.background_mass_window,
                        calibration_mass_window=self.calibration_mass_window,
                        calibrants_list=calibrants_list,
                        min_calibrant_number=self.min_calibrant_number,
                        min_calibrant_sn=calibration_sn_cutoff,
                        time=sum_spectrum.time,
                        time_window=sum_spectrum.time_window
                    )

                    # Write calibration plot to pdf.
                    if len(calibrants_list) > 0:
                        # Calibration was attempted
                        if mass_spectrum.data_calibrated is not None:
                            self.logger.info(
                                f"Calibrated sum spectrum ({mass_spectrum.time}"
                                f" ± {mass_spectrum.time_window} seconds) for "
                                f"{os.path.basename(path)}"
                            )
                        else:
                            self.logger.info(
                                f"Failed calibrating sum spectrum ({mass_spectrum.time}"
                                f" ± {mass_spectrum.time_window} seconds) for "
                                f"{os.path.basename(path)}"
                            )
                        # Save plot (success or failure) to PDF
                        if mass_spectrum.calibration_plot is not None:
                            pdf.savefig(mass_spectrum.calibration_plot)
                            plt.close(mass_spectrum.calibration_plot)
                            # Set plot to None to free up memory.
                            mass_spectrum.calibration_plot = None
                    else:
                        self.logger.info(
                            f"Skipped calibration of sum spectrum ({mass_spectrum.time}"
                            f" ± {mass_spectrum.time_window} seconds) for "
                            f"{os.path.basename(path)}"
                        )
                    
                    # Add mass spectrum to list.
                    mass_spectra.append(mass_spectrum)
                
                # Build a long table with quantitation results.
                output = ms_tables.build_quantitation_table(
                    filename=mzxml.file_name,
                    mass_spectra=mass_spectra,
                    analytes_ref=analytes_ref,
                    output_params=output_params,
                    use_peak_height=self.use_peak_height
                )
            
                # Append output to temporary CSV file.
                if not header:
                    output.to_csv(
                        temp_csv_path, mode="a", index=False, header=False
                    )
                else:
                    output.to_csv(
                        temp_csv_path, mode="a", index=False, header=True
                    )
                    header = False  # Only a header for the first processed file.
                
                # Update percentage of processed files.
                percent = round((idx + 1) / n * 100)
                self.quantitation_progress.emit(percent)

        # If no files produced output, the temp CSV is empty.
        # Avoid pd.read_csv raising EmptyDataError; return None instead.
        if header:
            self.logger.warning(
                "No mzXML files contained data. Quantitation produced no results."
            )
            os.remove(temp_csv_path)
            return None

        # Read the accumulated CSV file and delete it.
        quantitation_results = pd.read_csv(temp_csv_path)
        os.remove(temp_csv_path)

        return quantitation_results

    def quantitate_xy_files(
            self,
            analytes_ref_path: str,
            xy_file_paths: list[str]
    ) -> pd.DataFrame | None:
        """
        Perform calibration and quantitation on .xy files (MS-only mode).

        Args:
            analytes_ref_path: Path to the analytes reference Excel file.
            xy_file_paths: List of paths to .xy files.
        
        Returns:
            Dataframe with quantitation results if processing finished for
            all files. None if batch process was aborted during quantitation.
        """
        # Read in analytes reference Excel file.
        # Then extract the data for the calibrants.
        analytes_ref = pd.read_excel(analytes_ref_path)
        ref_calibrants = analytes_ref[analytes_ref["calibrant"]]

        # Create a list with required output parameters.
        output_params = [
            "total_area_background_subtracted",
            "mass_error_ppm",
            "isotopic_pattern_quality",
            "signal_to_noise",
            "total_area",
            "total_background",
            "total_noise"
        ]

        # Set path to pdf file with calibration figures.
        pdf_path = os.path.join(
            self.raw_folder_path,
            f"{self.start_time}_calibration.pdf"
        )

        # Set path to temporary CSV file for accumulating results.
        temp_csv_path = os.path.join(
            self.raw_folder_path,
            f"{self.start_time}_temp_results.csv"
        )
        # Delete existing CSV file if it exists.
        if os.path.exists(temp_csv_path):
            self.logger.info("Removing existing temporary results file")
            os.remove(temp_csv_path)
        # Ensure the temp CSV starts fresh.
        with open(temp_csv_path, "w", newline="") as f:
            pass

        # Loop over xy file paths and create mass spectra.
        # Keep track of number of processed files.
        n = len(xy_file_paths)
        header = True  # Set to false after first non-empty file is processed.
        with PdfPages(pdf_path) as pdf:
            for idx, path in enumerate(xy_file_paths):
                # Check if stop was requested.
                if self.stop_requested:
                    self.logger.info("BatchWorker stop requested during quantitation")
                    self.aborted.emit()
                    return None

                # Read xy file.
                # If empty, show warning and continue to next file.
                try:
                    file_name = os.path.splitext(os.path.basename(path))[0]
                    data_uncalibrated = self.read_xy_file(path)
                except ValueError:
                    self.logger.warning(
                        f"{file_name}.xy contains no data. "
                        "Continuing with the next file."
                    )
                    percent = round((idx + 1) / n * 100)
                    self.quantitation_progress.emit(percent)
                    continue

                # Determine calibration for MS-only mode.
                # Calibrate if calibrants are specified in the analytes list.
                if len(ref_calibrants) > 0:
                    # All calibrants apply in MS-only mode (no time filtering).
                    calibrants_df = (
                        ref_calibrants
                        .assign(
                            # Extract charge number from peak name.
                            charge = lambda x: (
                                x["peak"].str.split("_").str[1].astype(int)
                            )
                        )
                        # Select required columns.
                        [["mz", "charge", "mz_window"]]
                    )

                    # Create a list with (m/z, charge, m/z window) tuples.
                    calibrants_list = list(calibrants_df.itertuples(
                        index=False, name=None
                    ))

                    # Use global calibrant S/N cutoff for MS-only calibration.
                    calibration_sn_cutoff = self.calibrant_sn_cutoff

                else:
                    # No calibrants -> skip calibration.
                    calibrants_list = []
                    calibration_sn_cutoff = None
                
                # Create an instance of MassSpectrum.
                # For MS-only mode, time and time_window are None.
                mass_spectrum = MassSpectrum(
                    name=file_name,
                    file_raw=file_name,
                    data_uncalibrated=data_uncalibrated,
                    background_mass_window=self.background_mass_window,
                    calibration_mass_window=self.calibration_mass_window,
                    calibrants_list=calibrants_list,
                    min_calibrant_number=self.min_calibrant_number,
                    min_calibrant_sn=calibration_sn_cutoff,
                    time=None,
                    time_window=None
                )

                # Write calibration plot to pdf.
                if len(calibrants_list) > 0:
                    # Calibration was attempted
                    if mass_spectrum.data_calibrated is not None:
                        self.logger.info(
                            f"Calibrated spectrum for {file_name}"
                        )
                    else:
                        self.logger.info(
                            f"Failed calibrating spectrum for {file_name}"
                        )
                    # Save plot (success or failure) to PDF
                    if mass_spectrum.calibration_plot is not None:
                        pdf.savefig(mass_spectrum.calibration_plot)
                        plt.close(mass_spectrum.calibration_plot)
                        # Set plot to None to free up memory.
                        mass_spectrum.calibration_plot = None
                else:
                    self.logger.info(
                        f"Skipped calibration of spectrum for {file_name}"
                    )
                
                # Build a long table with quantitation results.
                # For MS-only mode, we have a single mass spectrum per file.
                output = ms_tables.build_quantitation_table(
                    filename=file_name,
                    mass_spectra=[mass_spectrum],
                    analytes_ref=analytes_ref,
                    output_params=output_params,
                    use_peak_height=self.use_peak_height
                )
            
                # Append output to temporary CSV file.
                if not header:
                    output.to_csv(
                        temp_csv_path, mode="a", index=False, header=False
                    )
                else:
                    output.to_csv(
                        temp_csv_path, mode="a", index=False, header=True
                    )
                    header = False
                
                # Update percentage of processed files.
                percent = round((idx + 1) / n * 100)
                self.quantitation_progress.emit(percent)

        # If no files produced output, the temp CSV is empty.
        # Avoid pd.read_csv raising EmptyDataError; return None instead.
        if header:
            self.logger.warning(
                "No xy files contained data. Quantitation produced no results."
            )
            os.remove(temp_csv_path)
            return None

        # Read the accumulated CSV file and delete it.
        quantitation_results = pd.read_csv(temp_csv_path)
        os.remove(temp_csv_path)

        return quantitation_results

    def export_results(
            self,
            aligned: bool,
            quantitation_results: pd.DataFrame | None
    ) -> None:
        """Export the quantitation results to an Excel file, including
        global settings and calibration settings.

        Args:
            aligned: Indicates whether alignment was performed.
            quantitation_results: Dataframe with quantitation results.
        """
        global_settings_dict = {
            "SweetSuite version": __version__,
            "Batch process start time": self.start_time,
            "Charge carrier": self.charge_carrier,
            "Mass modifier": self.mass_modifier if self.mass_modifier is not None else "None",
            "Sum spectrum resolution": (
                "N/A - MS-only mode" if self.ms_only
                else self.sum_spectrum_resolution
            ),
            "Background mass window": self.background_mass_window,
            "Calibration mass window": self.calibration_mass_window,
            "Quantitation m/z window": self.quantitation_mz_window,
            "Min. calibrant number": self.min_calibrant_number,
            "Min. isotopic fraction": self.min_isotopic_fraction,
            "Quadratic m/z window": self.quadratic_mz_window,
            "Quadratic coefficients": (
                str(self.quadratic_coeffs) if self.quadratic_mz_window else "N/A"
            ),
            "Use peak heights": self.use_peak_height,
            "Alignment time window": (
                "N/A - MS-only mode" if self.ms_only
                else self.alignment_time_window
            ),
            "Alignment m/z window": (
                "N/A - MS-only mode" if self.ms_only
                else self.alignment_mz_window
            ),
            "Alignment S/N cutoff": (
                "N/A - MS-only mode" if self.ms_only
                else self.alignment_sn_cutoff
            ),
            "Alignment min. peaks": (
                "N/A - MS-only mode" if self.ms_only
                else self.alignment_min_peaks
            )
        }

        global_settings = pd.DataFrame([
            {"Setting": key, "Value": value}
            for key, value in global_settings_dict.items()
        ])

        if not aligned:
            alignment_features = None
        else:
            # Take alignment features dataframe and fill in the empty
            # setting values with the global settings.
            alignment_features = self.alignment_list_df.copy()
            alignment_features["mz_window"] = (
                alignment_features["mz_window"]
                .fillna(self.alignment_mz_window)
            )
            alignment_features["time_window"] = (
                alignment_features["time_window"]
                .fillna(self.alignment_time_window)
            )
            alignment_features["sn_cutoff"] = (
                alignment_features["sn_cutoff"]
                .fillna(self.alignment_sn_cutoff)
            )
            alignment_features["required"] = (
                alignment_features["required"].notna()
            )

        if quantitation_results is None:
            calibration_settings = None
        else:
            if self.ms_only:
                # MS-only mode: Show N/A for time-based settings
                calibration_settings = pd.DataFrame([{
                    "time": "N/A - MS-only mode",
                    "window": "N/A - MS-only mode",
                    "calibrate": "N/A - MS-only mode",
                    "sn_cutoff": "N/A - MS-only mode"
                }])
            else:
                # LC-MS mode: Show actual calibration settings per retention time range
                calibration_settings = pd.DataFrame([
                    {
                        "time": time_window[0],
                        "window": time_window[1],
                        "calibrate": params["calibrate"],
                        "sn_cutoff": (
                            params["sn_cutoff"] if params["calibrate"]
                            else "N/A"
                        )
                    }
                    for time_window, params in self.sum_spectra_calibration.items()
                ])

        utils.write_to_excel(
            out_path=self.excel_path,
            data_dict={
                "Data": quantitation_results,
                "Global settings": global_settings,
                "Alignment features": alignment_features,
                "Sum spectrum settings": calibration_settings
            }
        )

