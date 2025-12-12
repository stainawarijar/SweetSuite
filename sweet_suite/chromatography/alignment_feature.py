import numpy as np

from .eic import Eic


class AlignmentFeature:
    """Represents a specified alignment feature.

    An AlignmentFeature encodes a target defined by an exact m/z and an
    expected retention time. It provides method to get the feature's observed
    intensity and to create an extracted ion chromatogram (EIC).

    Attributes:
        mz_exact (float): Exact m/z value of the alignment feature.
        time_required (float): Retention time (seconds) to which the feature
            should be aligned.
        alignment_time_window (float): Time window around the required
            retention time within which to search for the observed time.
        alignment_mz_window (float): The m/z window (Th) to use around the 
            exact m/z of the feature to create when creating an EIC.
        sn_cutoff (float): Minimum chomatographic S/N value that the EIC
            feature must have to be used for alignment.
        required (bool): Indicates whether the feature is required for 
            for alignment. When `True`, the alignment of the corresponding
            chromatographic run will fail if the feature's S/N is below the
            specified cut-off.
    """

    def __init__(
            self,
            mz_exact: float,
            time_required: float,
            alignment_time_window: float,
            alignment_mz_window: float,
            alignment_sn_cutoff: float,
            required: bool
    ):
        """Initialize an alignment feature.

        Args:
            mz_exact: Exact m/z value of the alignment feature.
            time_required: Retention time (seconds) to which the feature
                should be aligned.
            alignment_time_window: Time window around the required
                retention time within which to search for the observed time.
            alignment_mz_window: The m/z window (Th) to use around the exact
                m/z of the feature to create when creating an EIC.
            alignment_sn_cutoff: Minimum chomatographic S/N value that the EIC
                feature must have to be used for alignment.
            required: Indicates whether the feature is required for 
                for alignment. When `True`, the alignment of the corresponding
                chromatographic run will fail if the feature's S/N is below the
                specified cut-off.
        """
        self.mz_exact = mz_exact
        self.time_required = time_required
        self.alignment_time_window = alignment_time_window
        self.alignment_mz_window = alignment_mz_window
        self.alignment_sn_cutoff = alignment_sn_cutoff
        self.required = required
    
    def get_intensity(
            self,
            mz_window: float,
            spectrum: np.ndarray
    ) -> float:
        """Find the observed intensity of the feature in one spectrum.

        The method searches the closed m/z interval
        [mz_exact - mz_window, mz_exact + mz_window] and returns the maximum
        intensity found in that interval. The input spectrum is expected to be
        sorted by m/z in ascending order.

        Args:
            mz_window: m/z window around the feature m/z.
            spectrum: 2D array with m/z values in column 0 and intensities
                in column 1. Must be sorted by m/z.

        Returns:
            The maximum intensity within the specified m/z window.
        """
        idx_low = np.searchsorted(
            spectrum[:, 0],
            self.mz_exact - mz_window,
            side="left"
        )
        idx_high = np.searchsorted(
            spectrum[:, 0],
            self.mz_exact + mz_window,
            side="right"
        )
        # TODO: Proper error handling.
        if idx_low == idx_high:
            return 0.0

        spectrum_subset = spectrum[idx_low:idx_high, :]
        return np.max(spectrum_subset[:, 1])
    
    def create_eic(
            self,
            times_spectra: list[tuple[float, np.ndarray]]
    ) -> Eic:
        """Create an extracted ion chromatogram for the alignment feature.
        
        Args:
            times_spectra: A list of tuples, each one containing a scan time
            (float) as its first element and a mass spectrum (2D array) as
            its second element.
        
        Returns:
            An extracted ion chromatogram as an instance of the `Eic` class.
        """
        # Initiate lists to collect times and intensities.
        times = []
        intensities = []

        # Loop over decoded mass spectra.
        for scan_time, spectrum in times_spectra:
            # Get maximum intensity within m/z tolerance.
            intensity = self.get_intensity(self.alignment_mz_window, spectrum)
            times.append(scan_time)
            intensities.append(intensity)

        # Combine times and intensities into a 2D array.
        data = np.column_stack((times, intensities))

        # Return instance of EIC.
        return Eic(
            mz_exact=self.mz_exact,
            data=data,
            time_required=self.time_required,
            alignment_time_window=self.alignment_time_window,
            alignment_sn_cutoff = self.alignment_sn_cutoff,
            required_for_alignment = self.required
        )