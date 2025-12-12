import numpy as np

from .isotopic_peak import IsotopicPeak


class Calibrant(IsotopicPeak):
    """Represents a calibrant peak with spline-based m/z refinement.

    Extends `IsotopicPeak` with calibration windows and a cubic-spline
    refinement to locate the observed m/z and signal within a mass
    window around the theoretical m/z.

    Attributes:
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
        spectrum: np.ndarray,
        integration_mz_window: float,
        calibration_mass_window: float
    ):
        """Initialize a calibrant peak.

        Args:
            mz_exact: Exact (theoretical) m/z of the peak.
            charge: Ion charge state.
            spectrum: 2D array with m/z and intensity columns.
            integration_mz_window: m/z window (Th) used for extraction.
            calibration_mass_window: Mass window (Da) used to compute the 
                calibration m/z window.
        """                                                                       
        super().__init__(mz_exact, charge, spectrum, integration_mz_window)
        self.calibration_mass_window = calibration_mass_window
        self.calibration_mz_window = self.get_calibration_mz_window()
        self.spline_maximum = self.get_spline_maximum(self.calibration_mz_window)
        self.mz_observed = self.get_mz_observed()
        self.signal = self.get_signal()

    def get_calibration_mz_window(self) -> float:
        """Return the calibration m/z window (Th)."""
        return self.calibration_mass_window / self.charge

    def get_mz_observed(self) -> float:
        """Return observed m/z from the spline maximum."""
        return float(self.spline_maximum[0])

    def get_signal(self) -> float:
        """Return signal (intensity) at the spline maximum."""
        return float(self.spline_maximum[1])
