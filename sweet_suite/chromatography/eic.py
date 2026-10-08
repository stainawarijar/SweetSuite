import numpy as np
import matplotlib.pyplot as plt

from .chromatogram import Chromatogram


class Eic(Chromatogram):
    """Represents an extracted ion chromatogram (EIC) created from an mzXML
    file, used for aligning LC-MS data.

    This class holds the raw chromatographic trace for a single m/z value.

    Attributes:
        mz_exact (float): Target mass-to-charge ratio for this chromatogram.
        time_required (float): Retention time to which the feature should
            be aligned.
        alignment_time_window (float): Time window to use around the required
            retention time to look for the observed retention time.
        alignment_sn_cutoff (float): Minimum chomatographic S/N value that 
            the EIC feature must have to be used for alignment.
        required_for_alignment (bool): Indicates whether the feature is 
            required for for alignment. When `True`, the alignment of the 
            corresponding chromatographic run will fail if the feature's S/N 
            is below the specified cut-off.
        peak_data (np.ndarray: Data of the EIC within the specified alignment
            time range.
        maximum (tuple[float, float]): (time, intensity) at the maximum within
            the peak window.
        signal_to_noise (float): Signal-to-noise ratio of feature computed as
            `(max_intensity - background) / noise`.
    """
    
    def __init__(
        self,
        data: np.ndarray,
        mz_exact: float,
        time_required: float,
        alignment_time_window: float,
        alignment_sn_cutoff: float,
        required_for_alignment: bool
    ):
        """Initialize an EIC instance.

        Args:
            data: Array of shape (N, 2) with time in column 0 and intensity
                in column 1, ordered from low to high time.
            mz_exact: Target mass-to-charge ratio for the EIC.
            time_required: A time value of interest (e.g., expected
                retention time). Stored for reference.
            alignment_time_window: Time window around the required
                retention time within which to search for the observed time.
            alignment_sn_cutoff: Minimum chomatographic S/N value that 
                the EIC feature must have to be used for alignment.
            required_for_alignment: Indicates whether the feature is 
                required for for alignment. When `True`, the alignment of the 
                corresponding chromatographic run will fail if the feature's 
                S/N is below the specified cut-off.
            
        """
        super().__init__(data)
        self.mz_exact = mz_exact
        self.time_required = time_required
        self.alignment_time_window = alignment_time_window
        self.alignment_sn_cutoff = alignment_sn_cutoff
        self.required_for_alignment = required_for_alignment

    @property
    def peak_data(self) -> np.ndarray:
        """Return data within the specified alignment time range."""
        start_idx = np.searchsorted(
            self.data[:, 0],
            self.time_required - self.alignment_time_window,
            side="left"
        )
        end_idx = np.searchsorted(
            self.data[:, 0],
            self.time_required + self.alignment_time_window,
            side="right"
        )
        # TODO: Proper error handling.
        if start_idx == end_idx:
            return np.empty((0, 2))

        return self.data[start_idx:end_idx, :]

    @property
    def maximum(self) -> tuple[float, float]:
        """Determines where the peak range data has a maximum intensity.

        The time where the intensity takes on a maximum is taken to be
        the observed retention time.

        Returns:
            A tuple of the form (retention time, intensity).
        """
        if len(self.peak_data) == 0:
            # TODO: Proper error handling.
            return (np.nan, np.nan)
        
        return tuple(self.peak_data[np.argmax(self.peak_data[:, 1])])

    @property
    def signal_to_noise(self) -> float:
        """Returns the signal-to-noise (S/N).
        
        The signal is calculated as the intensity minus the background area.
        In case of a negative signal-to-noise, zero is returned. Returns
        `np.nan` when noise is 0, or when background and/or noise are `nan`.
        """
        intensity = self.maximum[1]
        background = self.background_and_noise[0]
        noise = self.background_and_noise[1]

        try:
            sn = (intensity - background) / noise
        except ZeroDivisionError:
            return np.nan

        if sn > 0:
            return sn
        else:
            return 0.0
