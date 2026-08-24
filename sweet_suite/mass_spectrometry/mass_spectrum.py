import logging
import os

from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .analyte import Analyte
from .calibrant import Calibrant
from .isotopic_peak import IsotopicPeak


class MassSpectrum():
    """Represents a mass spectrum.

    A `MassSpectrum` stores uncalibrated m/z-intensity data and creates
    calibrant observations for the spectrum's retention-time window. It can
    fit a quadratic m/z calibration from explicitly assigned calibrants or
    apply supplied calibration coefficients. In LC-MS processing,
    `BatchWorker` pools calibrants across enabled sum spectra, fits one global
    calibration per mzXML file, and supplies that fit to every enabled sum
    spectrum. The class also provides methods for quantifying analytes,
    plotting the calibration, and exporting spectrum data.

    Attributes:
        name (str): Name used to identify the spectrum and create output
            filenames.
        file_raw (str): Name of the raw data file containing the spectrum.
        data_uncalibrated (np.ndarray): 2D array with uncalibrated m/z values
            in the first column and intensities in the second column.
        background_mass_window (float): Mass window (Da) used to estimate
            background and noise around peaks.
        calibrate (bool): Whether calibration was requested for the spectrum.
        calibration_mass_window (float): Mass window (Da) used to locate
            calibrant peaks.
        calibrants_df (pd.DataFrame): Potential calibrants, with `mz`,
            `charge`, and `mz_window` columns.
        time (float | None): Retention time of the spectrum; `None` for
            MS-only data.
        time_window (float | None): Retention-time window of the spectrum;
            `None` for MS-only data.
        local_calibrants (list[Calibrant]): Calibrants available within the
            spectrum's m/z range and retention-time window.
        calibrants_to_fit (list[Calibrant] | None): Calibrants used to fit the
            calibration model.
        plot_mz_corrections (bool): If true, the calibration plot shows m/z
            corrections instead of mass errors in ppm.
        data_calibrated (np.ndarray | None): Calibrated spectrum data, or
            `None` when calibration cannot be performed.
        calibration_plot (Figure | None): Plot of the calibration fit, or
            `None` when calibration cannot be performed.
    """

    def __init__(
        self,
        name: str,
        file_raw: str,
        data_uncalibrated: np.ndarray,
        background_mass_window: float,
        calibrate: bool,
        calibration_mass_window: float,
        calibrants_df: pd.DataFrame,
        time: float | None = None,
        time_window: float | None = None,
        calibrants_to_fit: list[Calibrant] | None = None,
        calibration_fit: np.ndarray | None = None,
        plot_mz_corrections: bool = False
    ):
        """Initialize a mass spectrum."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.name = name
        self.file_raw = file_raw
        self.data_uncalibrated = data_uncalibrated
        self.background_mass_window = background_mass_window
        self.calibrate = calibrate
        self.calibration_mass_window = calibration_mass_window
        self.calibrants_df = calibrants_df
        self.time = time
        self.time_window = time_window
        self.local_calibrants = self.get_local_calibrants()
        self.calibrants_to_fit = calibrants_to_fit
        self.calibration_fit = calibration_fit
        self.plot_mz_corrections = plot_mz_corrections
        self.apply_calibration()

    def apply_calibration(
        self,
        plot: bool = True,
        color_map: dict[
            tuple[float, float],
            tuple[float, float, float, float]
        ] | None = None
    ) -> None:
        """Calibrate the data using a calibration fit, but only if fit 
        coefficients or a list of calibrants to fit are provided.
        
        Args:
            plot: Whether to create a calibration figure or not. 
                Set to `True` by default.
            color_map: An optional dictionary that maps (time, window)
                combinations to colors. These are used for coloring
                data points in the calibration fit figure.

        The fitted coefficients are used to populate `data_calibrated` and
        `calibration_plot`. If a calibration fit is in `self.calibration_fit`
        then that fit is used. Otherwise, fitting is attempted on provided
        `self.calibrants_to_fit`. If neither are provided then `fit`,
        `self.data_calibrated` and `self.calibration_plot` are all `None`.
        """
        if self.calibration_fit is not None:
            fit = self.calibration_fit
        else:
            fit = self.fit_calibration()  # Based on `self.calibrants_to_fit`

        self.data_calibrated = self.calibrate_data(calibration_fit=fit)

        if plot:
            self.calibration_plot = self.plot_calibration(
                calibration_fit=fit, 
                color_map=color_map
            )
        else:
            self.calibration_plot = None

    def get_local_calibrants(self) -> list[Calibrant]:
        """Return a list with instances of the `Calibrant` class, whose 
        retention times correspond to the retention time of this MassSpectrum
        instance (if applicable).
        
        When no calibrants are provided in `self.calibrants_df`, or when
        `self.calibrate` is set to `False`, an empty list is returned.
        """
        if not self.calibrate:
            return []  # To prevent unnecessary work below.

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
                quantitation_mz_window=mz_window,
                calibration_mass_window=self.calibration_mass_window
            )

            calibrants.append(calibrant)
        
        return calibrants

    def fit_calibration(self) -> np.ndarray | None:
        """Fit an m/z calibration model using specified calibrants.

        The model predicts the required m/z correction `mz_exact - mz_observed`
        as a quadratic function of the observed m/z, using calibrants specified
        in `self.calibrants_to_fit`.

        Returns:
            An array containing the model coefficients [quadratic, linear, 
            intercept]. If `self.calibrants_to_fit` is `None` or an empty list, 
            `None` is returned.
        """ 
        calibrants = self.calibrants_to_fit

        if not calibrants:
            return

        mz_observed = np.array(
            [cal.mz_observed for cal in calibrants],
            dtype=float
        )

        mz_delta = np.array(
            [cal.mz_exact - cal.mz_observed for cal in calibrants],
            dtype=float
        )

        return np.polyfit(x=mz_observed, y=mz_delta, deg=2)

    def calibrate_data(
        self,
        calibration_fit: np.ndarray | None
    ) -> np.ndarray | None:
        """Calibrate spectrum based on the supplied calibration coefficients.

        The coefficients specify the amount by which each observed m/z value
        should be shifted. 

        Args:
            calibration_fit: Calibration coefficients in the order [quadratic, 
            linear, intercept].

        Returns:
            A 2D array containing calibrated m/z values in the first column
            and intensities in the second column. Returns `None` when
            `calibration_fit` is `None`.
        """
        if calibration_fit is None:
            return None

        data_calibrated = self.data_uncalibrated.copy()
        mz_observed = self.data_uncalibrated[:, 0]
        mz_shift = np.polyval(calibration_fit, mz_observed)
        data_calibrated[:, 0] += mz_shift

        return data_calibrated

    def plot_calibration(
        self,
        calibration_fit: np.ndarray | None,
        color_map: dict[
            tuple[float, float],
            tuple[float, float, float, float]
        ] | None = None
    ) -> Figure | None:
        """Plot the calibration fit.

        Required m/z corrections or mass errors (ppm) are plotted against the 
        observed m/z values. Calibrant data points are colored by their 
        retention time window if applicable. The quadratic fit is shown as a 
        smooth curve. The required calibrant m/z range is shown by light 
        shading.

        Args:
            calibration_fit: Quadratic fit coefficients in the order
                [quadratic, linear, intercept].
            color_map: An optional dictionary that maps (time, window)
                combinations to colors. 

        Returns:
            A matplotlib Figure. `None` if `calibration_fit` is `None`. `None`
            if `self.calibrants_to_fit` is `None` or empty.
        """
        if calibration_fit is None:
            return

        calibrants = self.calibrants_to_fit

        if not calibrants:
            return

        mz_exact = np.array(
            [cal.mz_exact for cal in calibrants],
            dtype=float
        )

        mz_observed = np.array(
            [cal.mz_observed for cal in calibrants],
            dtype=float
        )

        mz_delta = np.array(
            [cal.mz_exact - cal.mz_observed for cal in calibrants],
            dtype=float
        )

        # In case of LC-MS data, color by retention time.
        if self.time is None:
            color_by_time = False
        else:
            color_by_time = True

        # Create evenly spaced m/z values for drawing smooth fitted curve.
        mz_plot = np.linspace(mz_observed.min(), mz_observed.max(), 500)

        # Apply the fit to the specified m/z values.
        delta_fitted = np.polyval(calibration_fit, mz_plot)

        # Determine values to plot: m/z corrections or ppm errors.
        if not self.plot_mz_corrections:
            y_values = -mz_delta / mz_exact * 1e6
            y_fitted = (-delta_fitted / (mz_plot + delta_fitted) * 1e6)
            y_label = "Mass error (ppm)"
        else:
            y_values = mz_delta
            y_fitted = delta_fitted
            y_label = r"Required correction $\Delta m/z$"

        # Create figure.
        figure, axis = plt.subplots()

        if color_by_time:
            time_windows = np.array(
                [(cal.time, cal.time_window) for cal in calibrants],
                dtype=float
            )
            for time_value, window_value in np.unique(time_windows, axis=0):
                mask = (
                    (time_windows[:, 0] == time_value) &
                    (time_windows[:, 1] == window_value)
                )

                key = (float(time_value), float(window_value))

                axis.scatter(
                    mz_observed[mask],
                    y_values[mask],
                    s=45,
                    color=color_map[key] if color_map is not None else None,
                    edgecolor="black",
                    linewidths=0.4,
                    label=f"{time_value:g} ± {window_value:g} s"
                )
        else:
            axis.scatter(
                mz_observed,
                y_values,
                s=45,
                edgecolor="black",
                linewidths=0.4
            )

        axis.plot(mz_plot, y_fitted, color="black")

        axis.set_xlabel(r"Observed $m/z$")
        axis.set_ylabel(y_label)
        axis.set_title(f"{self.file_raw}")

        if color_by_time:
            axis.legend(
                title="Sum spectrum",
                loc="center left",
                bbox_to_anchor=(1.02, 0.5),
                fontsize=9,
                title_fontsize=9
            )

        axis.set_axisbelow(True)
        axis.grid(
            True,
            which="major",
            linewidth=0.5,
            alpha=0.2
        )

        figure.tight_layout()

        return figure

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
            analytes_ref: Reference data with one row per isotopic peak and
                columns `peak`, `mz`, `mz_window`, and `relative_area`.
                For LC-MS data, `time` and `time_window` columns identify the
                sum spectrum in which each peak should be quantified.
            use_peak_height: If True, use maximum intensity of each isotopic
                peak instead of the trapezoidal area for quantitation.
        
        Returns:
            A list with instances of the `Analyte` class.
            `None` if the mass spectrum failed to calibrate.
        """
        # Determine which MS data to use.
        if self.data_calibrated is not None:
            spectrum = self.data_calibrated
        elif self.calibrate:
            # Calibration failed, return `None`.
            return
        else:
            # No calibration, so use uncalibrated data.
            spectrum = self.data_uncalibrated
        
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
        # spectrum range. For every peak the quantitation window is checked;
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

            # Check that the quantitation window fits within the spectrum range.
            if mz_val - mz_window < mz_min or mz_val + mz_window > mz_max:
                analytes_to_skip.add(analyte_label)
                continue

            # For the first peak of each analyte, also check background window.
            if analyte_label != prev_analyte_label:
                background_half_span = (
                    self.background_mass_window / charge + mz_window
                )
                if (
                    mz_val - background_half_span < mz_min or 
                    mz_val + background_half_span > mz_max
                ):
                    analytes_to_skip.add(analyte_label)

            prev_analyte_label = analyte_label

        for label in analytes_to_skip:
            self.logger.warning(
                f"Analyte {label} falls outside the spectrum m/z range "
                "and will not be quantified."
            )

        self.skipped_analytes = analytes_to_skip
        if analytes_to_skip:
            reference = reference[
                ~reference["peak"].apply(
                    lambda p: "_".join(str(p).split("_")[:-1]) 
                    in analytes_to_skip
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
                quantitation_mz_window=row["mz_window"]
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
                            "peak", 
                            "mz_exact", 
                            "relative_area_theoretical",
                            "area", 
                            "maximum_intensity", 
                            "mass_error_ppm"
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
