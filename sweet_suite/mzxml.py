from pathlib import Path
import re
import zlib

from matplotlib.figure import Figure
import numpy as np
from scipy.interpolate import interp1d

from .chromatography import alignment
from .chromatography.alignment_feature import AlignmentFeature
from .chromatography.eic import Eic
from .mzxml_data_block import MzxmlDataBlock
from .sum_spectrum import SumSpectrum


class Mzxml:
    """Interface for reading and processing mzXML files.

    This class parses an mzXML file, extracts individual scans as 
    `MzxmlDataBlock` instances, and provides utilities to construct 
    retention time-resolved spectra and summed spectra over time ranges.
    In addition, it provides methods for retention time alignment.

    Attributes:
        path (str): Path to the mzXML file.
        file_name (str): File name without extension.
        times_bytes (list[float, dict]): A list of containing tuples 
            `(time, decoded_data)` where `time` is the retention time of an
            mzXML data block and `decoded_data` is a dictionary containing 
            decoded data (bytes), compression (bool), endian (str) and 
            encoding precision (str).
        retention_times (np.ndarray): 1D array with retention times of all
            MS scans.
    """

    def __init__(self, path: str):
        """Initialize an mzXML file reader.

        Args:
            path: Path to the mzXML file to be read.
        """
        self.path = path
        self.file_name = self.get_file_name()
        self.times_bytes = self.read_data_blocks()
        self.retention_times = self.get_retention_times()
    
    @staticmethod
    def create_mass_spectra(times_bytes: list[float, dict]) -> np.ndarray:
        """Creates mass spectra from compressed bytes data.

        Processes a list of retention time and bytes dictionary pairs to extract
        and decompress mass spectrometry data, converting it into 2D arrays
        containing m/z and intensity values.

        Args:
            times_bytes: List of tuples where each tuple contains a retention 
            time (float) and a dictionary with keys: 'bytes' (compressed data), 
            'compression' (bool), 'endian' (str), and 'precision' (str).

        Returns:
            List of tuples containing retention times and corresponding 2D 
            arrays with m/z values in the first column and intensity values 
            in the second column.
        """
        data_required = []
        for rt, bytes_dict in times_bytes:
            data = bytes_dict["bytes"]
            # Decompress if necessary.
            if bytes_dict["compression"]:
                data = zlib.decompress(data)
            # Get 1D array of data.
            data = np.frombuffer(data, dtype=(
                bytes_dict["endian"] + "f" + bytes_dict["precision"]
            ))
            # Turn into 2D array with m/z and intensity columns.
            data = np.vstack((data[::2], data[1::2])).T
            # Add to list.
            data_required.append((rt, data)) 
        
        return data_required

    def get_file_name(self) -> str:
        """Return extensionless file name from the file path."""
        return Path(self.path).stem

    def read_data_blocks(self) -> list[float, dict]:
        """Read data blocks from mzXML file.

        Returns:
            A list of containing tuples `(time, decoded_data)` where `time`
            is the retention time of a data block and `decoded_data` is 
            a dictionary containing decoded data (bytes), compression (bool),
            endian (str) and encoding precision (str).
        """
        times_bytes = []

        header = True  # mzXML files start with a header.
        with open(self.path, "r") as file:
            for line in file:
                # <scan num = "..."> represents the start of a scan.
                # </scan> represents the end of a scan.
                if "<scan num=" in line:
                    header = False  # Scan number 1 also means end of header.
                    # Start of a new block of data.
                    # Continue reading the next lines until </scan> is reached.
                    current_data_block = ""
                elif "</scan>" in line:
                    # End of the current data block.
                    # Create instance of MzXmlDataBlock class.
                    data_block = MzxmlDataBlock(current_data_block)
                    # Append data to list.
                    times_bytes.append((
                        data_block.retention_time, data_block.decoded_data
                    ))
                elif not header:
                    # Line part of current data block.
                    if not isinstance(current_data_block, str):
                        current_data_block = ""
                    current_data_block += line

        return times_bytes
    
    def get_retention_times(self) -> np.ndarray:
        """Return an array with all retention times."""
        return np.array([t for t, _ in self.times_bytes])

    def create_sum_spectrum(
        self,
        time: float,
        time_window: float,
        resolution: int
    ) -> SumSpectrum:
        """Create a sum spectrum based on a specified retention time range.

        Starts by generating an empty spectrum with equally sized m/z bins,
        where the number of bins per Th is specified by `resolution`.
        The sum spectrum bins are then filled by summing the intensities of all
        data points that have an m/z value larger than the lower edge of the
        bin and smaller than or equal to the upper edge of the bin, using all
        the spectra that fall within the specified retention time range.

        Args:
            time: Center of the desired retention time range.
            time_window: Retention time window around center.
            resolution: Number of data points per Th (m/z unit) used
                when creating the sum spectrum.

        Returns:
            A `SumSpectrum` of the specified retention time range.
        """
        # Get indices of spectra with lowest and highest required time.
        idx_low = np.searchsorted(
            self.retention_times,
            time - time_window,
            side="left"
        )
        idx_high = np.searchsorted(
            self.retention_times,
            time + time_window,
            side="right"
        )
        # TODO: Proper error handling.
        if idx_low == idx_high:
            return SumSpectrum(
                self.file_name, time, time_window, np.empty((0, 2))
            )

        # Extract the decoded data for this retention time range.
        times_bytes_required = self.times_bytes[idx_low:idx_high]

        # Convert the bytes into 2D mass spectrum.
        data_required = self.create_mass_spectra(times_bytes_required)

        # Determine the lowest and highest m/z values out of the spectra.
        min_mz = np.min([
            time_spectrum[1][0][0] for time_spectrum in data_required
        ])
        max_mz = np.max([
            time_spectrum[1][-1][0] for time_spectrum in data_required
        ])

        # Generate an empty spectrum with equally sized m/z bins.
        data_length = int((max_mz - min_mz) * resolution)
        mz_axis = np.linspace(min_mz, max_mz, data_length)
        intensity_axis = np.zeros(data_length)

        # Sum the spectra.
        for time_spectrum in data_required:
            # Get two tuples: one with m/z values, one with intensities.
            mzs, intensities = zip(*time_spectrum[-1])
            # Interpolation (piecewise linear spline).
            fit = interp1d(
                x=mzs, y=intensities,
                # Spectra generally don't cover the whole range of min_mz
                # to max_mz. Set `bounds_error` to False and `fill_value`
                # to 0 to handle that situation.
                bounds_error=False, fill_value=0
            )
            # Add to intensity axis.
            intensity_axis = np.add(intensity_axis, fit(mz_axis))

        # Combine m/z values and intensities into one spectrum.
        combined_spectrum = np.stack((mz_axis, intensity_axis), axis=-1)

        # Explicitly round m/z values and intensities to 8 decimal places.
        rounded = np.round(combined_spectrum, 8)

        return SumSpectrum(self.file_name, time, time_window, rounded)
    
    def get_alignment_fit_eics(
            self,
            alignment_features: list[AlignmentFeature],
            min_peaks: int
    ) -> tuple[np.ndarray | None, list[Eic]]:
        """Fit the required retention times as a function of observed
        retention times for a list of alignment features.

        This function takes a list of alignment features (each one having a 
        required retention time), and creates an extracted ion chromatogram 
        (EIC) for each of them. For each EIC, the observed retention time is
        determined. A power law (Y = a * X^b + c) is then fitted through the 
        (observed, required) data points. If power law fitting fails, a linear
        fit (Y = a*x + b) is used.
        
        Args:
            alignment_features: A list containing instances of the class
                `AlignmentFeature`.
            min_peaks: The minimum number of peaks above the S/N cut-off
                required for fitting / retention time alignment. 5 is an 
                absolute minimum.
        
        Returns:
            A tuple containing an array with fit coefficients as its first
            element and a list with instances of `Eic` as second element.
            The first element is `None` when curve fitting fails.
        """
        # Create 2D MS array for all retention times. 
        times_spectra = self.create_mass_spectra(self.times_bytes)

        # Create EICs for the alignment features.
        eics = []
        for feature in alignment_features:
            eic = feature.create_eic(times_spectra)
            if eic.signal_to_noise >= feature.alignment_sn_cutoff:
                eics.append(eic)
            elif eic.required_for_alignment:
                # Fail alignment if feature is required.
                # Empty EIC list and stop loop to force a failed alignment.
                eics = []
                break

        # Get power/linear fit coefficients.
        fit_coeffs = alignment.fit_power(
            eics=eics,
            min_peaks=min_peaks
        )

        return (fit_coeffs, eics)

    def plot_alignment_fit(
            self,
            fit_eics: tuple[np.ndarray | None, list[Eic]]
    ) -> Figure:
        """Visualize the curve fitting for retention alignment.

        See documentation of the `alignment.plot_fit` function for more
        details.

        Args:
            fit_eics: A tuple containing fit coefficients and a list of EICs,
                as returned by the function `get_alignment_fit_eics`.
        
        Returns:
            A matplotlib figure.
        """
        # Split into fit coefficients and the EICs.
        fit_coeffs, eics = fit_eics[0], fit_eics[1]

        # Check that fitting was successful.
        if fit_coeffs is None:
            return

        # Create the plot
        times_observed = [eic.maximum[0] for eic in eics]
        times_required = [eic.time_required for eic in eics]
        plot = alignment.plot_fit(
            times_observed=times_observed,
            times_required=times_required,
            fit_coeffs=fit_coeffs,
            title=self.file_name
        )
        
        return plot

    def align_retention_times(
            self,
            fit_eics: tuple[np.ndarray, list[Eic]]
    ) -> None:
        """Align retention times and write to a new mzXML file.

        This function takes the alignment fit and applies it to all observed
        retention times in the mzXML file. The adjusted retention times are
        written to a new mzXML file, whose name is that of the original mzXML
        with the prefix 'aligned_'. If alignment failed, an empty 'unaligned_'
        file is created.

        Args:
            fit_eics: A tuple containing fit coefficients and a list of EICs,
                as returned by the function `get_alignment_fit_eics`.
        """
        # Extract fit coefficients.
        fit_coeffs = fit_eics[0]

        # If fitting failed, write empty unaligned mzXML file.
        if fit_coeffs is None:
            path = Path(self.path)
            new_name = f"unaligned_{path.name}"
            new_path = str(path.with_name(new_name))
            open(new_path, "w").close()
            
            return

        # Adjust retention times based on fit.
        if len(fit_coeffs) == 3:
            # Power function: y = a + x^b + c
            a, b, c = fit_coeffs[0], fit_coeffs[1], fit_coeffs[2]
            times_aligned = a * self.retention_times**b + c
        else:
            # Linear function: y = ax + b
            a, b = fit_coeffs[0], fit_coeffs[1]
            times_aligned = a*self.retention_times + b
        
        # Create file path to aligned mzXML file.
        path = Path(self.path)
        new_name = f"aligned_{path.name}"
        new_path = str(path.with_name(new_name))

        # Write to new mzXML file.
        idx = 0
        with (
            open(self.path, "r") as old_file,
            open(new_path, "w") as new_file
        ):
            for line in old_file:
                if "retentionTime=" in line:
                    new_time = np.round(times_aligned[idx], 3)
                    adjusted_line = re.sub(
                            'retentionTime="[^"]+"', 
                            f'retentionTime="PT{new_time}S"',
                            line
                        )
                    new_file.write(adjusted_line)
                    idx += 1
                else:
                    new_file.write(line)




    
    
        