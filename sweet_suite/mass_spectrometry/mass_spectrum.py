import os

from matplotlib.figure import Figure
import numpy as np
import pandas as pd

from .analyte import Analyte
from .calibrant import Calibrant
from .isotopic_peak import IsotopicPeak
from .plotting import plot_polynomial


class MassSpectrum():
    """Represents a mass spectrum.

    Attributes:
        name (str): Name of the mass spectrum.
        file_raw (str): Name of the mzXML file from which the raw data 
            originates, excluding file extension.
        data_uncalibrated (np.ndarray): Array with uncalibrated MS data, 
            the first column containing m/z values and the second column
            containing intensities.
        background_mass_window (float): The mass window (Da) to be used
            for background determination around the monoisotopic peak.
        calibration_mass_window (float): Mass window (Da) used to compute the 
                calibration m/z window for each calibrant.
        calibrants_list (list[tuple[float, float, float]]): List with tuples 
            of the form `(m/z, charge, integration window)` for each calibrant.
        min_calibrant_number (int): Minimum number of calibrants required for 
            calibration. Calibration will fail if this threshold is not met.
        min_calibrant_sn (float): Minimum signal-to-noise required for
            a calibrant to actually be used for calibration.
        time (float | None): Retention time for which the sum spectrum was 
            created. Only applicable to LC data.
        time_window (float | None): Retention time window that was used around
            `time` to create the sum spectrum. Only applicable to LC data.
        calibrants (list[Calibrant]): List with instances of the `Calibrant`
            class. The list is empty when no calibration is performed.
        calibrated (tuple[np.ndarray, Figure] | tuple[None, None]): Tuple
            containing an array with calibrated data and a figure showing
            the calibration. (None, None) if calibration failed.
        data_calibrated (np.ndarray | None): Array with calibrated MS data.
            If calibration failed, this is set to `None`. When no calibration 
            was performed (an empty `calibrants` list), this will be set to 
            `data_uncalibrated`.
        calibration_plot: Figure showing calibration of the mass spectrum
            (observed vs required m/z fit).
    """

    def __init__(
            self,
            name: str,
            file_raw: str,
            data_uncalibrated: np.ndarray,
            background_mass_window: float,
            calibration_mass_window: float,
            calibrants_list: list[tuple[float, float, float]],
            min_calibrant_number: int,
            min_calibrant_sn: float,
            time: float | None,
            time_window: float | None
    ):
        """
        Initialize a mass spectrum.

        Args:
            name: Name of the mass spectrum.
            file_raw: Name of the mzXML file from which the raw data originates, 
                excluding file extension.
            data_uncalibrated: Array with uncalibrated MS data, the first 
                column containing m/z values and the second column containing 
                intensities.
            background_mass_window: The mass window (Da) to be used for 
                background determination around the monoisotopic peak.
            calibration_mass_window: Mass window (Da) used to compute the 
                calibration m/z window for each calibrant.
            calibrants_list: List with tuples of the form 
                `(m/z, charge, integration window)` for each calibrant.
            min_calibrant_number: The minimum number of calibrants required 
                for calibration. Calibration will fail if this threshold is
                not met.
            min_calibrant_sn: Minimum signal-to-noise required for a calibrant 
                to actually be used for calibration.
            time: Retention time for which the sum spectrum was created. 
                Only applicable to LC data.
            time_window: Retention time window that was used around `time` 
                to create the sum spectrum. Only applicable to LC data.
        """
        self.name = name
        self.file_raw = file_raw
        self.data_uncalibrated = data_uncalibrated
        self.background_mass_window = background_mass_window
        self.calibration_mass_window = calibration_mass_window
        self.calibrants_list = calibrants_list
        self.min_calibrant_number = min_calibrant_number
        self.min_calibrant_sn = min_calibrant_sn        
        self.time = time
        self.time_window = time_window
        self.calibrants = self.get_calibrants()
        self.calibrated = self.calibrate()
        self.data_calibrated = self.calibrated[0]
        self.calibration_plot = self.calibrated[1]

    def get_calibrants(self) -> list[Calibrant]:
        """Return a list with instances of the `Calibrant` class.
        
        When no calibrants are provided in `self.calibrants_list`,
        an empty list is returned.
        """
        calibrants = []
        for mz, charge, mz_window in self.calibrants_list:
            calibrant = Calibrant(
                mz_exact=mz,
                charge=charge,
                spectrum=self.data_uncalibrated,
                integration_mz_window=mz_window,
                calibration_mass_window=self.calibration_mass_window
            )
            calibrants.append(calibrant)
        
        return calibrants

    def calibrate(self) -> tuple[np.ndarray, Figure] | tuple[None, None]:
        """Calibrate mass spectrum based on a specified list of calibrants.

        Calibration is performed based on a list of exact m/z values
        of potential calibrant peaks. First, the observed m/z values
        of all the potential calibrants are determined. The S/N of each 
        observed calibrant peak is then calculated. For those calibrant 
        peaks whose S/N is above a specified cut-off (usually 9 or 27),
        if the number of peaks equals at least the specified minimum number 
        of calibrants (4 being the absolute minimum), a second-degree 
        polynomial is fitted through the pairs of exact and observed 
        m/z values. This polynomial is used to calibrate the mass spectrum.

        Returns:
            A tuple containing calibrated data and a figure visualizing the
            fitting. The calibrated data is a 2D array with adjusted m/z values 
            in one column and intensities in the second column. 
            Returns `None` if the minimum number of  calibrants is not reached, 
            or if the list with calibrants is empty.
        """
        # Check if calibrants were provided.
        if len(self.calibrants) == 0:
            return (None, None)

        # Create a list of observed m/z values for all calibrants
        # with a signal-to-noise valuea above the S/N cut-off.
        calibrants_above_cutoff = []
        for calibrant in self.calibrants:
            # Get background and noise data.
            background_and_noise = calibrant.get_background_and_noise(
                target_mz=calibrant.spline_maximum[0],
                background_mass_window=self.background_mass_window
            )
            # Check S/N > cut-off.
            background_average_intensity=background_and_noise[0] 
            noise = background_and_noise[2]
            if calibrant.signal > (
                background_average_intensity + self.min_calibrant_sn * noise
            ):
                calibrants_above_cutoff.append(calibrant)

        # Check against the minimum number of calibrants.
        if len(calibrants_above_cutoff) < self.min_calibrant_number:
            return (None, None)
    
        # Fit 2nd degree polynomial through (observed, exact) m/z pairs.
        mzs_observed = [cal.mz_observed for cal in calibrants_above_cutoff]
        mzs_exact = [cal.mz_exact for cal in calibrants_above_cutoff]
        fit = np.polyfit(x = mzs_observed, y=mzs_exact, deg=2)

        # Adjust m/z values using the fitted polynomial.
        poly_func = np.poly1d(fit)  # Polynomial function based on fit coeffs.
        mzs_adjusted = poly_func(self.data_uncalibrated[:, 0])

        # Visualize the calibration in a plot (similar to alignment).
        plot = plot_polynomial(mzs_observed, mzs_exact, poly_func, self.name)

        # Return calibrated spectrum and figure.
        data_calibrated = np.column_stack(
            (mzs_adjusted, self.data_uncalibrated[:, 1])
        )

        return (data_calibrated, plot)
        
    def quantify_analytes(
            self,
            analytes_ref: pd.DataFrame
    ) -> list[Analyte] | None:
        """Quantify analytes and calculate quality control parameters.

        Each molecule in a specific charge state is considered to be 
        a separate analyte. For each analyte the total background subtracted
        area is calculated. The following quality control parameters are 
        also determined: signal-to-noise (S/N), isotopic pattern quality 
        (IPQ), mass error in parts-per-million (ppm).
        
        Args:
            analytes_ref: A data frame with the following columns: ...
        
        Returns:
            A list with instances of the `Analyte` class.
            `None` if the mass spectrum failed to calibrate.
        """
        # Determine which MS data to use.
        if self.data_calibrated is None:
            if len(self.calibrants_list) != 0:
                # Calibration failed, return None.
                return None
            else:
                # No calibration, so use uncalibrated data.
                spectrum = self.data_uncalibrated
        else:
            spectrum = self.data_calibrated
        
        # In case of LC data: get analytes ref only for RT range.
        if (self.time is not None and self.time_window is not None):
            reference = (
                analytes_ref[
                    (analytes_ref["time"] == self.time) &
                    (analytes_ref["time_window"] == self.time_window)
                ]
            )
        else:
            reference = analytes_ref

        # Initialize list to which instances of Analyte will be added.
        analytes = []

        # Initialize analyte properties.
        current_analyte = None
        peaks = []
        background_and_noise = None

        # Loop over isotopologues in analytes reference df.
        for _, row in reference.iterrows():
            # Remove isotopologue number from 'peak' to get analyte name.
            analyte_name = "_".join(row["peak"].split("_")[:-1])

            # Create instance of IsotopicPeak.
            peak = IsotopicPeak(
                mz_exact=row["mz"],
                charge=int(row["peak"].split("_")[-2]),
                spectrum=spectrum,
                integration_mz_window=row["mz_window"]
            )

            # Check if analyte name has changed.
            if current_analyte != analyte_name:
                # Create instance of Analyte class for previous analyte, 
                # unless we are dealing with first analyte in the iteration.
                if current_analyte is not None: 
                    # Add previous analyte to list.
                    analytes.append(Analyte(
                        name=current_analyte.split("_")[0],
                        charge=int(current_analyte.split("_")[1]),
                        peaks=pd.DataFrame(peaks, columns=[
                            "peak", "mz_exact", "relative_area_theoretical",
                            "area", "maximum_intensity", "mass_error_ppm"
                        ]), 
                        background_and_noise=background_and_noise
                    ))
                    # Reset peaks list.
                    peaks = []
                
                # Update analyte name plus background and noise.
                # (Background and noise are based on the monoisotopic peak)
                current_analyte = analyte_name
                background_and_noise = peak.get_background_and_noise(
                    target_mz=peak.mz_exact,
                    background_mass_window=self.background_mass_window
                )
                
            # Extend list with peak areas.
            peaks.append({
                "peak": row["peak"],
                "mz_exact": row["mz"],
                "relative_area_theoretical": row["relative_area"],
                "area": peak.get_area(),
                "maximum_intensity": peak.get_maximum_intensity(),
                "mass_error_ppm": peak.get_mass_error_ppm()
            })

        # Add final analyte to list.
        analytes.append(Analyte(
            name=current_analyte.split("_")[0],
            charge=int(current_analyte.split("_")[1]),
            peaks=pd.DataFrame(peaks, columns=[
                "peak", "mz_exact", "relative_area_theoretical",
                "area", "maximum_intensity", "mass_error_ppm"
            ]), 
            background_and_noise=background_and_noise
        ))

        return analytes

    def write_xy(self, path: str) -> None:
        """Write m/z values and intensities to a '.xy' file.

        When the spectrum was calibrated, the calibrated data is written
        to a '.xy' file. If the spectrum was not calibrated, the uncalibrated
        data is written to a '.xy' file. 

        m/z values and intensities are rounded to 8 decimals.

        Args:
            path (str): Path to directory in which the '.xy' file is saved.
        """
        if self.data_calibrated is None:
            np.savetxt(
                os.path.join(path, f"uncalibrated_{self.name}.xy"),
                self.data_uncalibrated,
                delimiter="\t", fmt="%.8f"
            )
        else:
            np.savetxt(
                os.path.join(path, f"calibrated_{self.name}.xy"),
                self.data_calibrated,
                delimiter="\t", fmt="%.8f"
            )            