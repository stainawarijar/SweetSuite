from datetime import datetime
import logging
import os

import matplotlib
matplotlib.use("Agg")
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
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
            mzxml_folder_path: str | None,
            alignment_list_df: pd.DataFrame | None,
            alignment_time_window: float,
            alignment_mz_window: float,
            alignment_sn_cutoff: float,
            alignment_min_peaks: int,
            analytes_list_df: pd.DataFrame | None,
            sum_spectra_calibration: dict,
            charge_carrier: str,
            sum_spectrum_resolution: int,
            background_mass_window: float,
            calibration_mass_window: float,
            quantitation_mz_window: float,
            min_calibrant_number: int,
            min_isotopic_fraction: float,
            quantitate_aligned_only: bool,
            quadratic_mz_window: bool,
            quadratic_coeffs: tuple[float, float, float],
            parent = None
    ):
        super().__init__(parent)
        self.start_time = datetime.now().strftime("%d-%m-%Y_%H%M")
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info(f"\nBatchWorker initialized at {self.start_time}")
        self.blocks = blocks
        self.mzxml_folder_path = mzxml_folder_path
        self.alignment_list_df = alignment_list_df
        self.alignment_time_window = alignment_time_window
        self.alignment_mz_window = alignment_mz_window
        self.alignment_sn_cutoff = alignment_sn_cutoff
        self.alignment_min_peaks = alignment_min_peaks
        self.analytes_list_df = analytes_list_df
        self.sum_spectra_calibration = sum_spectra_calibration
        self.charge_carrier = charge_carrier
        self.sum_spectrum_resolution = sum_spectrum_resolution
        self.background_mass_window = background_mass_window
        self.calibration_mass_window = calibration_mass_window
        self.quantitation_mz_window = quantitation_mz_window
        self.min_calibrant_number = min_calibrant_number
        self.min_isotopic_fraction = min_isotopic_fraction
        self.quantitate_aligned_only = quantitate_aligned_only
        self.quadratic_mz_window = quadratic_mz_window
        self.quadratic_coeffs = quadratic_coeffs
        self.excel_path = self.get_output_excel_path()
        self.stop_requested = False

    def get_output_excel_path(self) -> str | None:
        """Set path to Excel file to which final results will be written.
        
        Returns:
            The path as a string, or None if the mzXML folder path does
            not exist (possible when only an analytes list is uploaded).
        """
        if self.mzxml_folder_path is None:
            return

        excel_path = os.path.join(
            self.mzxml_folder_path,
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
        if self.analytes_list_df is None:
            self.logger.info(
                "No analytes list provided, skipping reference file generation"
            )
            analytes_ref_path = None
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
        if self.mzxml_folder_path is None:
            if analytes_ref_path is None:
                message = ""
            else:
                message = f"Analytes reference file was created at {analytes_ref_path}"
            self.logger.warning("No batch directory selected")
            self.error.emit(
                    "Missing batch directory",
                    "Select a folder containing mzXML files.",
                    message,
                    "Warning"
                )
            self.finished.emit(False)
            return

        # Retention time alignment.
        if self.alignment_list_df is None:
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
                # Create new list with mzXML file paths.
                mzxml_file_paths = self.get_mzxml_file_paths()

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
    
    def make_ref_file(self) -> str:
        """Generate the analytes reference .xlsx file and return its path."""
        mzxml_folder_path=(
            os.getcwd() if self.mzxml_folder_path is None
            else self.mzxml_folder_path
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
                time=float(line.time),
                time_window=float(line.time_window),
                calibrant=(not pd.isnull(line.calibrant)),
                min_isotopic_fraction=self.min_isotopic_fraction,
                charge_carrier=self.charge_carrier
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
            mzxml_folder_path,
            f"{self.start_time}_analytes_ref.xlsx"
        )
        utils.write_to_excel(out_path, {"analytes": reference})

        return out_path
    
    def get_mzxml_file_paths(self) -> list[str]:
        """Collect all mzXML file paths from the specified folder."""
        mzxml_file_paths = []
        for file in os.listdir(self.mzxml_folder_path):
            if file.endswith(".mzXML"):
                full_path = os.path.join(self.mzxml_folder_path, file)
                mzxml_file_paths.append(full_path)
        
        return mzxml_file_paths

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
            self.mzxml_folder_path,
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
            self.mzxml_folder_path,
            f"{self.start_time}_calibration.pdf"
        )

        # Set path to temporary CSV file for accumulating results.
        # (Faster than writing to dataframes one-by-one to Excel).
        temp_csv_path = os.path.join(
            self.mzxml_folder_path,
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
        with PdfPages(pdf_path) as pdf:
            for idx, path in enumerate(mzxml_file_paths):
                # Check if stop was requested.
                if self.stop_requested:
                    self.logger.info("BatchWorker stop requested during quantitation")
                    self.aborted.emit()
                    return False

                # Read mzXML file.
                mzxml = Mzxml(path)

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
                    if mass_spectrum.calibration_plot is not None:
                        self.logger.info(
                            f"Calibrated sum spectrum ({mass_spectrum.time}"
                            f" ± {mass_spectrum.time_window} seconds) for "
                            f"{os.path.basename(path)}"
                        )
                        pdf.savefig(mass_spectrum.calibration_plot)
                        plt.close(mass_spectrum.calibration_plot)
                        # Set plot to None to free up memory.
                        mass_spectrum.calibration_plot = None

                    elif len(calibrants_list) > 0:
                        self.logger.info(
                            f"Failed calibrating sum spectrum ({mass_spectrum.time}"
                            f" ± {mass_spectrum.time_window} seconds) for "
                            f"{os.path.basename(path)}"
                        )
                    
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
                    output_params=output_params
                )
            
                # Append output to temporary CSV file.
                if idx > 0:
                    output.to_csv(
                        temp_csv_path, mode="a", index=False, header=False
                    )
                else:
                    output.to_csv(
                        temp_csv_path, mode="a", index=False, header=True
                    )
                
                # Update percentage of processed files.
                percent = round((idx + 1) / n * 100)
                self.quantitation_progress.emit(percent)

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
            "Sum spectrum resolution": self.sum_spectrum_resolution,
            "Background mass window": self.background_mass_window,
            "Calibration mass window": self.calibration_mass_window,
            "Quantitation m/z window": self.quantitation_mz_window,
            "Min. calibrant number": self.min_calibrant_number,
            "Min. isotopic fraction": self.min_isotopic_fraction,
            "Quadratic m/z window": self.quadratic_mz_window,
            "Quadratic coefficients": (
                str(self.quadratic_coeffs) if self.quadratic_mz_window else "N/A"
            ),
            "Alignment time window": self.alignment_time_window,
            "Alignment m/z window": self.alignment_mz_window,
            "Alignment S/N cutoff": self.alignment_sn_cutoff,
            "Alignment min. peaks": self.alignment_min_peaks
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

