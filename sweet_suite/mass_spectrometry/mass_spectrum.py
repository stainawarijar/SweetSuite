import logging
import os

from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .analyte import Analyte
from .calibrant import Calibrant
from .calibration import fit_calibration, plot_quadratic_calibration
from .isotopic_peak import IsotopicPeak


class MassSpectrum():
    """Represents a mass spectrum.

    TODO: FILL THIS IN...
    """

    def __init__(
        self,
        name: str,
        file_raw: str,
        data_uncalibrated: np.ndarray,
        background_mass_window: float,
        calibration_mass_window: float,
        calibrants_df: pd.DataFrame,
        time: float | None = None,
        time_window: float | None = None,
        global_calibration_fit: np.ndarray | None = None,
        local_calibrants_to_fit: list[dict] | None = None
    ):
        """Initialize a mass spectrum."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.name = name
        self.file_raw = file_raw
        self.data_uncalibrated = data_uncalibrated
        self.background_mass_window = background_mass_window
        self.calibration_mass_window = calibration_mass_window
        self.calibrants_df = calibrants_df
        self.time = time
        self.time_window = time_window
        self.calibrants = self.get_calibrants()
        self.global_calibration_fit = global_calibration_fit
        self.local_calibrants_to_fit = local_calibrants_to_fit

        # TODO: Perhapse this if-else can be removed?
        if self.global_calibration_fit is not None:
            self.apply_global_calibration()
        else:
            self.apply_local_calibration()

    def apply_global_calibration(self) -> None:
        """Calibrate the MS data by applying the global calibration fit."""
        self.data_calibrated = self.calibrate_data(self.global_calibration_fit)
        self.local_calibration_plot = None

    def apply_local_calibration(self) -> None:
        """Calibrate the data using a local calibration fit.
        
        If `self.local_calibrants_used` is `None` or an empty list, then
        `local_calibration_fit`, `data_calibrated` and `calibration_fit` will
        all be `None`.
        """
        fit = self.fit_calibration_local()
        self.data_calibrated = self.calibrate_data(fit)
        self.local_calibration_plot = self.plot_local_calibration(fit)

    def get_calibrants(self) -> list[Calibrant]:
        """Return a list with instances of the `Calibrant` class.
        
        When no calibrants are provided in `self.calibrants_df`,
        an empty list is returned.
        """
        # Create list of (m/z, charge, m/z window) tuples.
        tuples = list(
            self.calibrants_df.itertuples(index=False, name=None)
        )

        if not tuples:
            return []

        # Determine m/z boundaries of mass spectrum.
        mz_min = np.min(self.data_uncalibrated[:, 0])
        mz_max = np.max(self.data_uncalibrated[:, 0])

        calibrants = []
    
        for mz, charge, mz_window in tuples:

            # Check m/z value is not outside MS range.
            half_span = max(
                self.calibration_mass_window / charge,
                self.background_mass_window / charge + mz_window
            )
            if mz - half_span < mz_min or mz + half_span > mz_max:
                self.logger.warning(
                    f"Calibrant m/z {mz:.4f} is outside the spectrum m/z range "
                    "and will not be used."
                )
                continue
            
            # Create instance of Calibrant and add to list.
            calibrant = Calibrant(
                mz_exact=mz,
                charge=charge,
                time=self.time,
                time_window = self.time_window,
                spectrum=self.data_uncalibrated,
                background_mass_window=self.background_mass_window,
                integration_mz_window=mz_window,
                calibration_mass_window=self.calibration_mass_window
            )

            calibrants.append(calibrant)
        
        return calibrants

    def fit_calibration_local(self) -> np.ndarray | None:
        """Fit a quadratic m/z calibration model using local calibrants."""
        return fit_calibration(self.local_calibrants_to_fit)

    def calibrate_data(
        self,
        calibration_fit: np.ndarray | None
    ) -> np.ndarray | None:
        """Calibrate spectrum based on the supplied calibration coefficients.

        The coefficients specify the amount by which each observed m/z value
        should be shifted. A three-coefficient fit depends only on m/z, while
        a four-coefficient fit also includes retention time.

        Args:
            calibration_fit: Calibration coefficients. Expected formats are:
                - Three coefficients: [quadratic_mz, linear_mz, intercept]
                - Four coefficients: [quadratic_mz, linear_mz, time, intercept]

        Returns:
            A 2D array containing calibrated m/z values in the first column
            and intensities in the second column. Returns `None` when
            `calibration_fit` is `None`.
        
        Raises:
            ValueError: If the fit does not contain three or four coefficients.
        """
        if calibration_fit is None:
            return None

        if len(calibration_fit) not in [3, 4]:
            raise ValueError(
                "`calibration_fit` must contain either 3 coefficients "
                "(m/z only) or 4 coefficients (m/z and time)."
            )

        data_calibrated = self.data_uncalibrated.copy()
        mz_observed = self.data_uncalibrated[:, 0]

        if len(calibration_fit) == 3:
            mz_shift = np.polyval(calibration_fit, mz_observed)
        else:
            quadratic_mz, linear_mz, time, intercept = calibration_fit
            mz_shift = (
                quadratic_mz * mz_observed**2
                + linear_mz * mz_observed
                + time * self.time
                + intercept
            )

        data_calibrated[:, 0] += mz_shift

        return data_calibrated

    def plot_local_calibration(
        self,
        local_fit: np.ndarray | None
    ) -> Figure | None:
        """Plot the local calibration fit.

        Required m/z corrections are plotted against the observed m/z values.
        Calibrant data points are colored by their retention time if applicable.
        The quadratic fit is shown as a smooth curve.

        Args:
            local_fit: Array containing the quadratic m/z fit coefficients in 
                descending order: [quadratic, linear, intercept].
        
        Returns:
            A matplotlib Figure, as generated by `plot_quadratic_calibration`.
        """
        return plot_quadratic_calibration(
            calibrants=self.local_calibrants_to_fit, 
            fit=local_fit,
            title=f"{self.file_raw} - ({self.time} ± {self.time_window} s)"
        )
        
    def quantify_analytes(
        self,
        analytes_ref: pd.DataFrame,
        use_peak_height: bool = False
    ) -> list[Analyte] | None:
        """Quantify analytes and calculate quality control parameters.

        Each molecule in a specific charge state is considered to be 
        a separate analyte. For each analyte the total background subtracted
        area is calculated. The following quality control parameters are 
        also determined: signal-to-noise (S/N), isotopic pattern quality 
        (IPQ), mass error in parts-per-million (ppm).
        
        Args:
            analytes_ref: A data frame with the following columns: ...
            use_peak_height: If True, use maximum intensity of each isotopic
                peak instead of the trapezoidal area for quantitation.
        
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

        # Check that all required m/z windows for each analyte fit within the
        # spectrum range. For every peak the integration window is checked;
        # for the first (lowest-mass) peak per analyte the background window is
        # also checked, because background is determined from that peak.
        mz_min = np.min(spectrum[:, 0])
        mz_max = np.max(spectrum[:, 0])
        analytes_to_skip = set()
        prev_analyte_label = None
        for _, row in reference.iterrows():
            peak_name = str(row["peak"])
            mz_val = row["mz"]
            mz_window = row["mz_window"]
            charge = int(peak_name.split("_")[-2])
            analyte_label = "_".join(peak_name.split("_")[:-1])
            if analyte_label in analytes_to_skip:
                continue
            # Check that the integration window fits within the spectrum range.
            if mz_val - mz_window < mz_min or mz_val + mz_window > mz_max:
                analytes_to_skip.add(analyte_label)
                continue
            # For the first peak of each analyte, also check the background window.
            if analyte_label != prev_analyte_label:
                background_half_span = self.background_mass_window / charge + mz_window
                if mz_val - background_half_span < mz_min or mz_val + background_half_span > mz_max:
                    analytes_to_skip.add(analyte_label)
            prev_analyte_label = analyte_label
        for label in analytes_to_skip:
            self.logger.warning(
                f"Analyte {label} falls outside the spectrum m/z range and will not be quantified."
            )
        self.skipped_analytes = analytes_to_skip
        if analytes_to_skip:
            reference = reference[
                ~reference["peak"].apply(
                    lambda p: "_".join(str(p).split("_")[:-1]) in analytes_to_skip
                )
            ]

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
                        background_and_noise=background_and_noise,
                        use_peak_height=use_peak_height
                    ))
                    # Reset peaks list.
                    peaks = []
                
                # Update analyte name plus background and noise.
                # (Background and noise are based on the lowest-mass peak)
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
            background_and_noise=background_and_noise,
            use_peak_height=use_peak_height
        ))

        return analytes

    def write_xy(
        self,
        folder: str,
        calibration_enabled: bool = True,
        write_on_failure: bool = True
    ) -> None:
        """Write m/z values and intensities to a '.xy' file.

        The filename and data written depend on whether calibration was
        performed and whether it succeeded:

        - Calibration disabled (`calibration_enabled=False`): writes
        uncalibrated data to `{name}.xy` (no prefix).
        - Calibration enabled and successful: writes calibrated data to
        `calibrated_{name}.xy`.
        - Calibration enabled but failed: writes uncalibrated data to
        `uncalibrated_{name}.xy`, unless `write_on_failure` is
        `False`, in which case nothing is written.

        m/z values and intensities are rounded to 8 decimals.

        Args:
            folder: Path to directory in which the '.xy' file is saved.
            calibration_enabled: Whether calibration was attempted for this
                spectrum. When `False`, uncalibrated data is written
                without a prefix.
            write_on_failure: When calibration was enabled but failed,
                write the uncalibrated data with an `uncalibrated_` prefix.
                When `False`, nothing is written on failure.
        """
        if not calibration_enabled:
            np.savetxt(
                os.path.join(folder, f"{self.name}.xy"),
                self.data_uncalibrated,
                delimiter="\t", fmt="%.8f"
            )
        elif self.data_calibrated is not None:
            np.savetxt(
                os.path.join(folder, f"calibrated_{self.name}.xy"),
                self.data_calibrated,
                delimiter="\t", fmt="%.8f"
            )
        elif write_on_failure:
            np.savetxt(
                os.path.join(folder, f"uncalibrated_{self.name}.xy"),
                self.data_uncalibrated,
                delimiter="\t", fmt="%.8f"
            )
