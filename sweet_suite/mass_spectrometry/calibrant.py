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
        background_mass_window (float): ...
        calibration_mass_window (float): Mass window (Da) used to derive 
            the calibration m/z window.
        calibration_mz_window (float): m/z window (Th), equal to
            `calibration_mass_window / charge`.
        spline_maximum (tuple[float, float]): (m/z, intensity) at the
            spline-derived maximum within the window.
        mz_observed (float): Observed m/z at the spline maximum.
        signal (float): Signal (intensity) at the spline maximum.
    """

    def __init__(
        self,
        mz_exact: float,
        charge: int,
        time: float | None,
        time_window: float | None,
        spectrum: np.ndarray,
        background_mass_window: float,
        integration_mz_window: float,
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
            spectrum: 2D array with m/z and intensity columns.
            background_mass_window: ...
            integration_mz_window: m/z window (Th) used for extraction.
            calibration_mass_window: Mass window (Da) used to compute the 
                calibration m/z window.
        """                                                                       
        super().__init__(mz_exact, charge, spectrum, integration_mz_window)
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
        return self.calibration_mass_window / self.charge

    def get_mz_observed(self) -> float:
        """Return observed m/z from the spline maximum."""
        return float(self.spline_maximum[0])

    def get_signal(self) -> float:
        """Return signal (intensity) at the spline maximum."""
        return float(self.spline_maximum[1])
    
    def get_signal_to_noise(self) -> float:
        """Return signal-to-noise of the calibrant peak."""
        # Get background and noise data.
        background_and_noise = self.get_background_and_noise(
            target_mz=self.spline_maximum[0],
            background_mass_window=self.background_mass_window
        )
        # Calculate S/N
        background_avg_intensity = background_and_noise[0] 
        noise = background_and_noise[2]
        sn = (self.signal - background_avg_intensity) / noise

        return sn
