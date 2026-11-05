import numpy as np

from .isotopic_peak import IsotopicPeak


class Calibrant(IsotopicPeak):
    """Represents a calibrant peak with spline-based m/z refinement.

    Extends `IsotopicPeak` with calibration windows and a cubic-spline
    refinement to locate the observed m/z and signal within a mass
    window around the theoretical m/z.

    Attributes:
        time (float | None): Retention time of corresponding sum spectrum.
            `None` in case of MS-only data.
        time_window (float | None): Retention-time half-window in seconds,
            or `None` for MS-only data.
        background_mass_window (float): Mass window (Da) used to estimate
            background and noise around the calibrant peak.
        calibration_mass_window (float): Mass window (Da) used to derive 
            the calibration m/z window.
        calibration_mz_window (float): m/z window (Th), equal to
            `calibration_mass_window / abs(charge)`.
        spline_maximum (tuple[float, float]): (m/z, intensity) from
            `get_spline_maximum()`, or `(np.nan, np.nan)` if unavailable.
        mz_observed (float): Observed m/z at the spline maximum.
        signal (float): Signal (intensity) at the spline maximum.
        signal_to_noise (float): Background-subtracted signal divided by noise,
            estimated around `mz_observed` using the quantitation bin width.
            Zero for non-positive signal; `np.nan` for unusable maxima or
            backgrounds, or positive signal with zero/non-finite noise.
    """

    def __init__(
        self,
        mz_exact: float,
        charge: int,
        time: float | None,
        time_window: float | None,
        spectrum: np.ndarray,
        background_mass_window: float,
        quantitation_mz_window: float,
        calibration_mass_window: float
    ):
        """Initialize a calibrant peak.

        Args:
            mz_exact: Exact (theoretical) m/z of the peak.
            charge: Ion charge state.
            time: Retention time of corresponding sum spectrum. Set to `None`
                in case of MS-only data.
            time_window: Retention time window of the corresponding sum 
                spectrum. Set to `None` in case of MS-only data.
            spectrum: Nonempty 2D array with m/z and intensity columns, sorted
                by increasing m/z. The caller checks search-window coverage.
            background_mass_window: Mass window (Da) used to estimate
                background and noise around the calibrant peak.
            quantitation_mz_window: Extraction and background-bin half-width
                (Th), independent of the calibration search half-width.
            calibration_mass_window: Mass window (Da) used to compute the 
                calibration m/z window.
        """                                                                       
        super().__init__(mz_exact, charge, spectrum, quantitation_mz_window)
        self.time = time
        self.time_window = time_window
        self.background_mass_window = background_mass_window
        self.calibration_mass_window = calibration_mass_window
        self.calibration_mz_window = self.get_calibration_mz_window()
        self.spline_maximum = self.get_spline_maximum(self.calibration_mz_window)
        self.mz_observed = self.get_mz_observed()
        self.signal = self.get_signal()
        self.signal_to_noise = self.get_signal_to_noise()

    def get_calibration_mz_window(self) -> float:
        """Return the calibration m/z window (Th)."""
        return self.calibration_mass_window / abs(self.charge)

    def get_mz_observed(self) -> float:
        """Return observed m/z from the spline maximum."""
        return float(self.spline_maximum[0])

    def get_signal(self) -> float:
        """Return signal (intensity) at the spline maximum."""
        return float(self.spline_maximum[1])

    def get_signal_to_noise(self) -> float:
        """Return signal-to-noise of the calibrant peak.
        
        Returns:
        - S/N value of the calibrant peak as a float.
        - `0.0` in case of a non-positive background-subtracted signal.
        - `np.nan` when background-subtracted signal is positive but noise
            is zero or non-finite, the maximum is unavailable, or background
            cannot be determined.
        """
        if not np.all(np.isfinite((self.mz_observed, self.signal))):
            return np.nan
        
        try:
            background_and_noise = self.get_background_and_noise(
                target_mz=self.mz_observed,
                background_mass_window=self.background_mass_window
            )
        except ValueError as exc:
            self.logger.warning(
                f"Could not determine calibrant {self.mz_exact} S/N: {exc}"
            )
            return np.nan
        
        background_avg_intensity = background_and_noise[0] 
        noise = background_and_noise[2]

        signal_minus_background = self.signal - background_avg_intensity

        if signal_minus_background <= 0:
            return 0.0

        if noise == 0 or not np.isfinite(noise):
            return np.nan

        return signal_minus_background / noise
