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
            information for the monoisotopic peak of the analyte: 
            `(average background intensity, background area, noise)`.
        mz_monoisotopic (float): Monoisotopic m/z value.
        isotopic_fraction (float): Theoretical fraction of the isotopic 
            pattern that was integrated.
        mass_error_ppm (float): Mass error in parts per million (ppm), based on 
            the isotopic peak with the highest theoretical relative area.
        total_area (float): Total observed area of the integrated isotopic
            peaks.
        total_background (float): Total background area of the analyte.
        total_noise (float): Total noise of the analyte.
        total_area_background_subtracted (float): Total background 
            subtracted area of the analyte.
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
            background_and_noise: tuple[float, float, float]
    ):
        """Initialize an analyte.

        Args:
            name: Name of the analyte, excluding charge state and isotopologue
                number.
            charge: Charge state of the analyte.
            peaks: A DataFrame with the following columns: `peak`, `mz_exact`,
                `relative_area_theoretical`, `area`, `mass_error_ppm`.
            background_and_noise: A tuple containing the following information
                for the monoisotopic peak of the analyte:
                `(average background intensity, background area, noise)`.
        """
        self.name = name
        self.charge = charge
        self.peaks = peaks
        self.background_and_noise = background_and_noise
        self.mz_monoisotopic = self.get_mz_monoisotopic()
        self.isotopic_fraction = self.get_isotopic_fraction()
        self.mass_error_ppm = self.get_mass_error_ppm()
        self.total_area = self.get_total_area()
        self.total_background = self.get_total_background()
        self.total_noise = self.get_total_noise()
        self.total_area_background_subtracted = self.get_total_area_background_subtracted()
        self.signal_to_noise = self.get_signal_to_noise()
        self.isotopic_pattern_quality = self.get_isotopic_pattern_quality()

    def get_mz_monoisotopic(self) -> float:
        """Return the exact m/z value of the monoisotopic peak."""
        return self.peaks.iloc[0]["mz_exact"]

    def get_isotopic_fraction(self) -> float:
        """Return the fraction of the isotopic pattern that was integrated."""
        return np.sum(self.peaks["relative_area_theoretical"])

    def get_mass_error_ppm(self) -> float:
        """Return the mass error in parts per million (ppm).
        
        The mass error of the analyte is taken to be the mass error
        of the isotopic peak with the highest theoretical relative area.
        """
        mass_error_ppm = self.peaks.loc[
            self.peaks["relative_area_theoretical"].idxmax(), "mass_error_ppm"
        ]

        return mass_error_ppm

    def get_total_area(self) -> float:
        """Return the sum of the isotopologue areas."""
        areas_sum = np.sum(self.peaks["area"])
        # In case of negative result, return zero.
        if areas_sum > 0:
            return areas_sum
        else:
            return float(0)
    
    def get_total_background(self) -> float:
        """Return total background area of the analyte.
        
        The background area of the analyte is calculated as the monoisotopic
        background area multiplied by the total number of isotopic peaks.
        """
        total_background = self.background_and_noise[1] * len(self.peaks)
        # In case of negative result, return zero.
        if total_background > 0:
            return total_background
        else:
            return float(0)
    
    def get_total_noise(self) -> float:
        """Return the total noise for the analyte.
        
        The noise of analyte is calculated as the noise of the monoisotopic
        peak multiplied by the total number of isotopic peaks.
        """
        total_noise = self.background_and_noise[2] * len(self.peaks)
        # In case of negative result, return zero.
        if total_noise > 0:
            return total_noise
        else:
            return float(0)

    def get_total_area_background_subtracted(self) -> float:
        """Return the background subtracted total area.
        
        The monoisotopic background area is subtracted from the area of each 
        isotopic peak. The resulting positive background subtracted areas are
        summed to yield the total background subtracted area of the analyte.
        """
        background_area = self.background_and_noise[1]
        areas = self.peaks["area"] - background_area
        areas_sum = np.sum(areas[areas > 0])
        # In case of negative result, return zero.
        if areas_sum > 0:
            return areas_sum
        else:
            return float(0)

    def get_signal_to_noise(self) -> float:
        """Return the signal-to-noise (S/N).
        
        The S/N of the analyte is taken to be the S/N of the isotopic peak
        with the highest theoretical relative area. 

        In case of a negative signal-to-noise, zero is returned. Returns 
        `np.inf` when noise is zero and signal is greater than zero.
        """
        # Get noise and average background intensity.
        average_background_intensity = self.background_and_noise[0]
        noise = self.background_and_noise[2]

        # Get maximum intensity for the most abundant isotopic peak.
        maximum_intensity = self.peaks.loc[
            self.peaks["relative_area_theoretical"].idxmax(), 
            "maximum_intensity"
        ]

        # Calculate S/N.
        try:
            sn = (maximum_intensity - average_background_intensity) / noise
        except ZeroDivisionError:
            sn = np.inf
        
        # In case of negative result, return zero.
        if sn > 0:
            return sn
        else:
            return float(0)

    def get_isotopic_pattern_quality(self) -> float:
        """
        Return the isotopic pattern quality (IPQ).

        For each isotopic peak, the absolute difference between the expected
        relative area and the observed relative area is taken. The resulting
        absolute differences are then summed to yield the IPQ.
        """
        # Re-normalize the theoretical relative areas of the isotopic peaks.
        # This is required because in practice only a selection of isotopic
        # peaks is integrated.
        relative_areas_theoretical = (
            self.peaks["relative_area_theoretical"] / 
            np.sum(self.peaks["relative_area_theoretical"])
        )

        # Calculate observed background subtracted areas of isotopic peaks.
        # Resulting negative values are set to zero.
        background =  self.background_and_noise[1]
        areas_observed = np.maximum(self.peaks["area"] - background, 0)

        # Calculate observed relative areas.
        try:
            relative_areas_observed = (
                areas_observed / self.total_area_background_subtracted
            )
        except ZeroDivisionError:
            return None

        # Calculate absolute differences between theoretical and observed
        # relative areas, and sum the values.
        ipq = np.sum(
            abs(relative_areas_observed - relative_areas_theoretical)
        )

        return ipq
        
    
