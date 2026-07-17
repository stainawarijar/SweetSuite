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
        total_background (float): Total background of the analyte.
        total_noise (float): Total noise of the analyte.
        total_area_background_subtracted (float): Total background 
            subtracted area (or summed peak heights) of the analyte.
        signal_to_noise (float): The signal-to-noise (S/N) of the analyte,
            based on the isotopic peak with the highest theoretical relative 
            area.
        isotopic_pattern_quality (float): Isotopic pattern quality (IPQ)
            of the analyte.
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
        The resulting positive values are summed.
        """
        col = "maximum_intensity" if self.use_peak_height else "area"
        bg = self.background_and_noise[0 if self.use_peak_height else 1]
        values = self.peaks[col] - bg
        values_sum = np.sum(values[values > 0])
        # In case of negative result, return zero.
        if values_sum < 0:
            return 0.0
        return values_sum

    def get_signal_to_noise(self) -> float:
        """Return the signal-to-noise (S/N).
        
        The S/N of the analyte is taken to be the S/N of the isotopic peak
        with the highest theoretical relative area. 

        Returns:
            S/N value of the analyte as a float.
            `0.0` in case of a negative S/N value.
            `0.0` if background subtracted intensity is zero (analyte not
            present).
            `np.nan` when noise is non-positive (edge case that should
            not happen).
        """
        # If background subtracted intensity is 0, the analyte is not there
        # and we return `np.nan`
        if self.total_area_background_subtracted == 0:
            return 0.0

        # Get noise and average background intensity.
        average_background_intensity = self.background_and_noise[0]
        noise = self.background_and_noise[2]

        # Check for non-positive noise.
        if noise <= 0:
            # TODO: Log a warning message.
            # NOTE: Negative should not be possible because noise is calculated
            # as a standard deviation of data points.
            return np.nan
        
        # Get maximum intensity for the most abundant isotopic peak.
        maximum_intensity = self.peaks.loc[
            self.peaks["relative_area_theoretical"].idxmax(), 
            "maximum_intensity"
        ]
        
        # Calculate S/N.
        sn = (maximum_intensity - average_background_intensity) / noise

        # In case of negative result, return zero.
        if sn < 0:
            return 0.0
        return sn
    
    def get_mass_error_ppm(self) -> float:
        """Return the mass error in parts per million (ppm).
        
        The mass error of the analyte is taken to be the mass error
        of the isotopic peak with the highest theoretical relative area.

        If the analyte background-subtracted area is zero, `np.nan` is 
        returned because the analyte is not present.
        """
        if self.total_area_background_subtracted == 0:
            return np.nan

        mass_error_ppm = self.peaks.loc[
            self.peaks["relative_area_theoretical"].idxmax(), "mass_error_ppm"
        ]

        return mass_error_ppm

    def get_isotopic_pattern_quality(self) -> float:
        """
        Return the isotopic pattern quality (IPQ).

        For each isotopic peak, the absolute difference between the expected
        relative area and the observed relative area is taken. The resulting
        absolute differences are then summed to yield the IPQ.

        Returns `np.nan` if the analyte background-subtracted signal is zero.
        """
        # If background-subtracted area of the analyte is zero,
        # then the IPQ is undefined. Return NaN.
        if self.total_area_background_subtracted == 0:
            return np.nan

        # Re-normalize the theoretical relative areas of the isotopic peaks.
        # This is required because in practice only a selection of isotopic
        # peaks is integrated.
        relative_areas_theoretical = (
            self.peaks["relative_area_theoretical"] / 
            np.sum(self.peaks["relative_area_theoretical"])
        )

        # Calculate observed background subtracted areas of isotopic peaks.
        # Resulting negative values are set to zero.
        col = "maximum_intensity" if self.use_peak_height else "area"
        bg = self.background_and_noise[0 if self.use_peak_height else 1]
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
    