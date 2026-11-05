import logging

import numpy as np
import pandas as pd


class Analyte:
    """Represents a molecule in a specific charge state.
    
    Attributes:
        name (str): Name of the analyte, excluding charge state and isotopologue
            number.
        charge (int): Charge state of the analyte.
        peaks (pd.DataFrame): DataFrame with the following columns: `peak`, 
            `mz_exact`, `relative_area_theoretical`, `area`, `maximum_intensity`
            and `mass_error_ppm`.
        background_and_noise (tuple): Tuple containing the following 
            information for the lowest-mass peak of the analyte: 
            `(average background intensity, background area, noise)`.
        use_peak_height (bool): If True, use maximum intensity instead of
            trapezoidal area for quantitation.
        isotopic_fraction (float): Theoretical fraction of the isotopic 
            pattern that was integrated.
        mass_error_ppm (float): Mass error in parts per million (ppm), based on 
            the isotopic peak with the highest theoretical relative area.
        total_area (float): Total observed area (or summed peak heights) of the
            integrated isotopic peaks.
        total_background (float): Shared per-peak background area (or average
            intensity in peak-height mode) multiplied by the peak count.
        total_noise (float): Shared intensity noise multiplied by the peak count,
            in either quantitation mode.
        total_area_background_subtracted (float): Total background 
            subtracted area (or summed peak heights) of the analyte.
        signal_to_noise (float): The signal-to-noise (S/N) of the analyte,
            based on the isotopic peak with the highest theoretical relative 
            area.
        isotopic_pattern_quality (float): Sum of absolute differences between
            normalized theoretical and background-subtracted observed isotope
            fractions. Lower values indicate a closer match.
    """

    def __init__(
        self,
        name: str,
        charge: int,
        peaks: pd.DataFrame,
        background_and_noise: tuple[float, float, float],
        use_peak_height: bool = False
    ):
        """Initialize an analyte.

        Args:
            name: Name of the analyte, excluding charge state and isotopologue
                number.
            charge: Charge state of the analyte.
            peaks: A DataFrame with the following columns: `peak`, `mz_exact`,
                `relative_area_theoretical`, `area`, `maximum_intensity`,
                `mass_error_ppm`.
            background_and_noise: A tuple containing the following information
                for the lowest-mass peak of the analyte:
                `(average background intensity, background area, noise)`.
            use_peak_height: If True, use the maximum intensity of each
                isotopic peak instead of the trapezoidal area for quantitation.
                Background subtraction is performed using the average background
                intensity instead of the background area. Defaults to False.
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.name = name
        self.charge = charge
        self.peaks = peaks
        self.background_and_noise = background_and_noise
        self.use_peak_height = use_peak_height
        self.isotopic_fraction = self.get_isotopic_fraction()
        self.total_area = self.get_total_area()
        self.total_background = self.get_total_background()
        self.total_noise = self.get_total_noise()
        self.total_area_background_subtracted = (
            self.get_total_area_background_subtracted()
        )
        self.signal_to_noise = self.get_signal_to_noise()
        self.mass_error_ppm = self.get_mass_error_ppm()
        self.isotopic_pattern_quality = self.get_isotopic_pattern_quality()

    def get_isotopic_fraction(self) -> float:
        """Return the fraction of the isotopic pattern that was integrated."""
        return np.sum(self.peaks["relative_area_theoretical"])
    
    def get_total_area(self) -> float:
        """Return the sum of the isotopologue areas (or peak heights).
        
        When `self.use_peak_height` is True, the sum of maximum intensities is
        returned instead of the sum of trapezoidal areas.
        """
        col = "maximum_intensity" if self.use_peak_height else "area"
        values_sum = np.sum(self.peaks[col])
        # In case of negative result, return zero.
        if values_sum < 0:
            return 0.0
        return values_sum
    
    def get_total_background(self) -> float:
        """Return total background of the analyte.
        
        In area mode: background area multiplied by number of isotopic peaks.
        In peak-height mode: average background intensity multiplied by number
        of isotopic peaks.
        """
        # [0] = average background intensity, [1] = background area
        bg = self.background_and_noise[0 if self.use_peak_height else 1]
        total_background = bg * len(self.peaks)
        # In case of negative result, return zero.
        if total_background < 0:
            return 0.0
        return total_background
    
    def get_total_noise(self) -> float:
        """Return the total noise for the analyte.
        
        The noise of analyte is calculated as the noise of the lowest-mass
        peak multiplied by the total number of isotopic peaks.
        """
        total_noise = self.background_and_noise[2] * len(self.peaks)
        # In case of negative result, return zero.
        if total_noise < 0:
            return 0.0
        return total_noise

    def get_total_area_background_subtracted(self) -> float:
        """Return the background subtracted total area (or peak heights).
        
        In area mode: the lowest-mass background area is subtracted from the
        area of each isotopic peak.
        In peak-height mode: the average background intensity is subtracted
        from the maximum intensity of each isotopic peak.
        The resulting positive values are summed. Returns `np.nan` with a
        warning if peak values, background, or the calculated total are
        non-finite.
        """
        col = "maximum_intensity" if self.use_peak_height else "area"
        bg = self.background_and_noise[0 if self.use_peak_height else 1]
        if not np.isfinite(bg) or not np.isfinite(self.peaks[col]).all():
            self.logger.warning(
                f"Background-subtracted total is undefined for analyte {self.name} "
                f"(charge {self.charge}): peak {col} values or background "
                "contain non-finite values. Returning NaN."
            )
            return np.nan

        with np.errstate(over="ignore", invalid="ignore"):
            values = self.peaks[col] - bg
            values_sum = np.sum(values[values > 0])
        if not np.isfinite(values_sum):
            self.logger.warning(
                f"Background-subtracted total is undefined for analyte {self.name} "
                f"(charge {self.charge}): the calculated total is non-finite. "
                "Returning NaN."
            )
            return np.nan
        # In case of negative result, return zero.
        if values_sum < 0:
            return 0.0
        return values_sum

    def get_most_abundant_peak_index(self, metric: str):
        """Return the peak index, or warn if theoretical abundances are invalid."""
        theoretical = self.peaks["relative_area_theoretical"]
        theoretical_total = np.sum(theoretical)
        if (not np.isfinite(theoretical).all()
                or not np.isfinite(theoretical_total)
                or theoretical_total <= 0):
            self.logger.warning(
                f"{metric} is undefined for analyte {self.name} "
                f"(charge {self.charge}): theoretical isotope abundances "
                "contain non-finite values or have a non-positive total; "
                "the most abundant isotopic peak cannot be determined. Returning NaN."
            )
            return None
        return theoretical.idxmax()

    def get_signal_to_noise(self) -> float:
        """Return the signal-to-noise (S/N) of the analyte.
        
        The S/N of the analyte is taken to be the S/N of the isotopic peak
        with the highest theoretical relative abundance.

        Returns:
            - S/N value of the analyte as a float.
            - `0.0` in case of a non-positive background-subtracted signal.
            - `0.0` if background-subtracted analyte area is zero (analyte 
            assumed to not be present).
            - `np.nan` when background-subtracted signal is positive but noise
                is zero or non-finite.
        """
        # If background subtracted area of analyte is zero, assume the analyte 
        # is not there and return zero for S/N.
        if self.total_area_background_subtracted == 0:
            return 0.0

        # Get maximum intensity for the most abundant isotopic peak.
        peak_index = self.get_most_abundant_peak_index("S/N")
        if peak_index is None:
            return np.nan
        maximum_intensity = self.peaks.loc[peak_index, "maximum_intensity"]

        # Get noise and average background intensity.
        background_avg_intensity = self.background_and_noise[0]
        noise = self.background_and_noise[2]

        # Calculate background-subtracted signal.
        signal_minus_background = maximum_intensity - background_avg_intensity

        if not np.isfinite(signal_minus_background):
            self.logger.warning(
                f"S/N is undefined for analyte {self.name} "
                f"(charge {self.charge}): the background-subtracted signal "
                "of the most abundant isotopic peak is non-finite. Returning NaN."
            )
            return np.nan

        # If background subtracted signal is non-positive, return zero.
        if signal_minus_background <= 0:
            return 0.0

        # Guard against zero or non-finite noise values.
        if noise == 0 or not np.isfinite(noise):
            self.logger.warning(
                f"S/N is undefined for analyte {self.name} "
                f"(charge {self.charge}): noise is zero or non-finite "
                f"({noise}). Returning NaN."
            )
            return np.nan
        
        # Return signal-to-noise
        signal_to_noise = signal_minus_background / noise
        if not np.isfinite(signal_to_noise):
            self.logger.warning(
                f"S/N is undefined for analyte {self.name} "
                f"(charge {self.charge}): the calculated ratio is non-finite. "
                "Returning NaN."
            )
            return np.nan
        return signal_to_noise
    
    def get_mass_error_ppm(self) -> float:
        """Return the mass error in parts per million (ppm).
        
        The mass error of the analyte is taken to be the mass error
        of the isotopic peak with the highest theoretical relative area.

        If the analyte background-subtracted area is zero, `np.nan` is
        returned because the analyte is not present. A non-finite total also
        returns `np.nan`, with a warning identifying the analyte.
        """
        if self.total_area_background_subtracted == 0:
            return np.nan

        if not np.isfinite(self.total_area_background_subtracted):
            self.logger.warning(
                f"Mass error is undefined for analyte {self.name} "
                f"(charge {self.charge}): the total background-subtracted "
                "signal is non-finite. Returning NaN."
            )
            return np.nan

        peak_index = self.get_most_abundant_peak_index("Mass error")
        if peak_index is None:
            return np.nan
        mass_error_ppm = self.peaks.loc[peak_index, "mass_error_ppm"]

        if np.isnan(mass_error_ppm):
            self.logger.warning(
                f"Mass error is NaN for analyte {self.name} "
                f"(charge {self.charge}): the most abundant isotopic peak "
                "returned NaN."
            )

        return mass_error_ppm

    def get_isotopic_pattern_quality(self) -> float:
        """
        Return the isotopic pattern quality (IPQ).

        Normalize theoretical abundances over the selected isotopologues.
        Subtract the shared background from each measured area (or peak height),
        clip negative values to zero, and normalize by their sum. Sum the
        absolute differences between theoretical and observed fractions.

        Returns `np.nan` if the analyte background-subtracted signal is zero.
        """
        # If background-subtracted area of the analyte is zero,
        # then the IPQ is undefined. Return NaN.
        if self.total_area_background_subtracted == 0:
            self.logger.warning(
                f"IPQ is undefined for analyte {self.name} "
                f"(charge {self.charge}): the total background-subtracted "
                "signal is zero. Returning NaN."
            )
            return np.nan

        col = "maximum_intensity" if self.use_peak_height else "area"
        bg = self.background_and_noise[0 if self.use_peak_height else 1]
        if (not np.isfinite(self.total_area_background_subtracted)
                or not np.isfinite(bg)
                or not np.isfinite(self.peaks[col]).all()):
            self.logger.warning(
                f"IPQ is undefined for analyte {self.name} "
                f"(charge {self.charge}): the observed signal or background "
                "contains non-finite values. Returning NaN."
            )
            return np.nan

        theoretical = self.peaks["relative_area_theoretical"]
        theoretical_total = np.sum(theoretical)
        if (not np.isfinite(theoretical).all()
                or not np.isfinite(theoretical_total)
                or theoretical_total <= 0):
            self.logger.warning(
                f"IPQ is undefined for analyte {self.name} "
                f"(charge {self.charge}): theoretical isotope abundances "
                "contain non-finite values or have a non-positive total. "
                "Returning NaN."
            )
            return np.nan

        # Re-normalize the theoretical relative areas of the isotopic peaks.
        # This is required because in practice only a selection of isotopic
        # peaks is integrated.
        relative_areas_theoretical = (
            theoretical / theoretical_total
        )

        # Calculate observed background subtracted areas of isotopic peaks.
        # Resulting negative values are set to zero.
        areas_observed = np.maximum(self.peaks[col] - bg, 0)

        # Calculate observed relative areas.
        relative_areas_observed = (
            areas_observed / self.total_area_background_subtracted
        )

        # Calculate absolute differences between theoretical and observed
        # relative areas, and sum the values.
        ipq = np.sum(
            abs(relative_areas_observed - relative_areas_theoretical)
        )

        return ipq
