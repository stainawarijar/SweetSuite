from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import numpy as np
from scipy.interpolate import InterpolatedUnivariateSpline

from ..resources.constants import ISOTOPES


class IsotopicPeak:
    """Represents an isotopic peak in a mass spectrum.

    An `IsotopicPeak` stores the exact m/z value, charge state, spectrum, 
    and extraction window. It provides methods to estimate the local background 
    and noise around the peak.
    
    Attributes:
        mz_exact (float): The exact m/z value of the isotopic peak.
        charge (int): Charge state of the ion.
        spectrum (np.ndarray): 2D NumPy array with two columns: 
            m/z values and intensities.
        integration_mz_window (float): m/z window (Th) used for extracting the 
            peak from the spectrum.
        data (np.ndarray): 2D array with MS data of the spectrum in the 
            m/z range `[mz_exact ± integration_mz_window]`.
    """

    def __init__(
        self,
        mz_exact: float,
        charge: int,
        spectrum: np.ndarray,
        integration_mz_window: float
    ):
        """Initialize an isotopic peak.

        Args:
            mz_exact: The exact m/z value of the isotopic peak.
            charge: Charge state of the ion.
            spectrum: 2D NumPy array with m/z values and intensities.
            integration_mz_window: m/z window (Th) used for extracting the 
                peak from the spectrum.
        """
        self.mz_exact = mz_exact
        self.charge = charge
        self.spectrum = spectrum
        self.integration_mz_window = integration_mz_window
        self.data = self.get_data()

    def get_data(self) -> np.ndarray:
        """Return an array with the MS data in the m/z range
        [exact m/z ± integration window].
        """
        idx_low = np.searchsorted(
            self.spectrum[:, 0], 
            self.mz_exact - self.integration_mz_window, 
            side="left"
        )
        idx_high = np.searchsorted(
            self.spectrum[:, 0], 
            self.mz_exact + self.integration_mz_window, 
            side="right"
        )

        return self.spectrum[idx_low:idx_high, :]
    
    def get_area(self) -> float:
        """Integrate the region [exact m/z ± integration window] using the
        trapezoidal tule and return the total area. 
        """
        return np.trapezoid(y=self.data[:, 1], x=self.data[:, 0])

    def get_maximum_intensity(self) -> float:
        """Return the maximum intensity of the spectrum in the m/z range
        `[mz_exact ± integration_mz_window]`.
        """
        return np.max(self.data[:, 1])

    def get_background_and_noise(
        self,
        target_mz: float,
        background_mass_window: float
    ) -> tuple[float, float, float]:
        """Determine the background and noise for an isotopic peak.

        In the range [`target_mz` ± `background_mass_window` / z], a number of 
        m/z regions are defined and integrated. The centers of the regions are 
        separated by (1.00335 / z), corresponding to the mass difference between 
        13C and 12C, with 'z' being the charge state. Each region has a width of
        twice `self.integration_mz_window`.

        For all possible 5 consecutive regions, the average intensity is 
        calculated. The set of 5 bins with the lowest average intensity are 
        taken as the background region. Their areas are averaged to yield the 
        background area, and the noise is estimated as the standard deviation
        of intensities in those bins.

        Args:
            target_mz: m/z value for which background and noise should be 
                determined.
            background_mass_window: Mass window (Da) around `target_mz`. The 
                actual m/z window is divided by the charge state.

        Returns:
            A tuple of (background average intensity, background area, noise).
        """
        # Mass difference (Da) between carbon-13 and carbon-12.
        C13_C12_mass_diff = (
            ISOTOPES["carbon"]["C13"]["mass"]
            - ISOTOPES["carbon"]["C12"]["mass"]
        )

        # Define background m/z window (Th).
        background_mz_window = background_mass_window / self.charge

        # Create array from -window to +window in steps of 1/z.
        mz_steps = np.arange(
            start=-background_mz_window,
            stop=background_mz_window + 1 / self.charge,
            step=1 / self.charge
        )

        # Collect bin data.
        bins = []

        for step in mz_steps:
            # Define center of bin.
            mz_center = target_mz + step * C13_C12_mass_diff

            # Get data for this bin.
            idx_low = np.searchsorted(
                self.spectrum[:, 0], 
                mz_center - self.integration_mz_window, 
                side="left"
            )
            idx_high = np.searchsorted(
                self.spectrum[:, 0], 
                mz_center + self.integration_mz_window, 
                side="right"
            )
            bin_data = self.spectrum[idx_low:idx_high]
            bin_area = np.trapezoid(y=bin_data[:, 1], x=bin_data[:, 0])
            bins.append((bin_area, bin_data[:, 1]))

        # Find 5 consecutive bins with lowest average intensity.
        background_average_intensity = np.inf
        
        for i in range(len(bins) - 4):
            intensities = np.concatenate((
                bins[i][1], bins[i + 1][1], bins[i + 2][1],
                bins[i + 3][1], bins[i + 4][1]
            ))

            intensities_average = np.average(intensities)

            if intensities_average < background_average_intensity:
                background_average_intensity = intensities_average
                background_area = np.average([
                    bins[i][0], bins[i + 1][0], bins[i + 2][0], 
                    bins[i + 3][0], bins[i + 4][0]
                ])
                noise = np.std(intensities, ddof=1)

        return (background_average_intensity, background_area, noise)
    
    def get_spline_maximum(
            self,
            mz_window: float
    ) -> tuple[float, float]:
        """Find the (m/z, intensity) tuple for which the intensity has a
        maximum value within the specified m/z range.

        A cubic spline is fitted over the MS data in the range
        `[mz_exact ± mz_window]`. The m/z that yields the
        maximum predicted intensity is returned. If spline fitting fails,
        a non-fitted local maximum is used instead.

        Args:
            mz_window: m/z window (Th) to use around the exact
                m/z value (`self.mz_exact`). For quantitation, this
                should be equal to `integration_mz_window`. In case of
                calibration, this should be equal to `calibration_mz_window`.
        
        Returns:
            (m/z, intensity) tuple at the maximum within specified m/z range.
        """
        # Get MS data for the specified range.
        idx_low = np.searchsorted(
            self.spectrum[:, 0],
            self.mz_exact - mz_window,
            side="left"
        )
        idx_high = np.searchsorted(
            self.spectrum[:, 0],
            self.mz_exact + mz_window,
            side="right"
        )
        # TODO: Proper error handling.
        if idx_low == idx_high:
            return (self.mz_exact, 0.0)

        data_mz_range = self.spectrum[idx_low:idx_high]

        mzs = data_mz_range[:, 0]
        intensities = data_mz_range[:, 1]

        # Query grid for spline evaluation.
        n_query = max(int((mzs[-1] - mzs[0]) * 2500), 10)
        mz_array = np.linspace(start=mzs[0], stop=mzs[-1], num=n_query)

        # Initialize with the mid-point of the query grid.
        max_pair = (mz_array[len(mz_array) // 2], 0.0)

        try:
            # Fit cubic spline and evaluate.
            spline = InterpolatedUnivariateSpline(
                x=mzs, y=intensities, k=3
            )
            predicted = spline(mz_array)

            for idx, intensity in enumerate(predicted):
                if intensity > max_pair[1]:
                    max_pair = (mz_array[idx], float(intensity))

            return max_pair

        except ValueError:
            # Fallback: use non-fitted local maximum in the window.
            for idx, intensity in enumerate(intensities):
                if intensity > max_pair[1]:
                    max_pair = (mzs[idx], float(intensity))

            return max_pair

    def get_mass_error_ppm(self) -> float:
        """Return mass error in parts per million (ppm) based on the
        exact m/z and the observed m/z.

        The m/z value for which the fitted spline has a maximum intensity
        is taken to be the observed m/z.

        The mass error is calculated as: `(observed - exact) / exact * 1e6`
        """
        # Get observed m/z based on spline maximum.
        spline_maximum = self.get_spline_maximum(self.integration_mz_window)
        mz_observed = spline_maximum[0]

        # Calculate mass error
        mass_error_ppm = (mz_observed - self.mz_exact) / self.mz_exact * 1e6

        return mass_error_ppm
    
    def plot(self, title: str) -> Figure:
        """Plot the peak data.

        The exact m/z, specified integration window and the integrated area
        are all indicated.

        Args:
            title: Title for the plot.
        """
        x, y = self.data[:, 0], self.data[:, 1]
        
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.set_xlabel("$m/z$")
        ax.set_ylabel("Intensity")
        ax.plot(x, y, linestyle="-", color="black")
        ax.axvline(x=self.mz_exact, color="blue", label="Exact m/z")
        ax.axvline(x=self.mz_exact - self.integration_mz_window, color="red", label="Integration window")
        ax.axvline(x=self.mz_exact + self.integration_mz_window, color="red")
        ax.fill_between(self.data[:, 0], 0, self.data[:, 1], color ="black", alpha=0.3, label="Integrated area")
        ax.set_title(title)
        ax.legend(loc="upper left", framealpha=1)
        ax.ticklabel_format(useOffset=False)  # Prevents scientific notation on m/z axis.

        return fig
