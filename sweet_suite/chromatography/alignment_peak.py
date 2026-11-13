import logging

import numpy as np


class AlignmentPeak:
    """Represents a specified alignment peak in LC-FLD data.
    
    ...
    """

    def __init__(
        self,
        peak: str,
        time: float,
        time_window: float,
        sn_cutoff: float,
        required: bool
    ):
        """Initialize an alignment peak.
        
        ...
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.peak = peak
        self.time_required = time
        self.alignment_time_window = time_window
        self.alignment_sn_cutoff = sn_cutoff
        self.required = required

    def get_info(
        self, 
        data: np.ndarray,
        background: float,
        noise: float
    ) -> tuple[float, float]:
        """Determines the observed retention time and signal-to-noise of the
        alignment peak.

        The time where the intensity takes on a local maximum is taken to be
        the observed retention time.

        Args:
            data: 2D array containing all chromatogram data in the
                retention time region of interest.
            background: background value of the chromatogram data.
            noise: noise value for the chromatogram background.
            
        Returns:
            A tuple of the form (observed time, S/N). If no local maximum could 
            be found, `(np.nan, np.nan)` is returned.
        """
        # Select region of chromatogram data in which to look for the peak.
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
        # TODO: Proper error handling
        if start_idx == end_idx:
            return (np.nan, np.nan)

        data_window = data[start_idx:end_idx]
        times = data_window[:, 0]
        intensities = data_window[:, 1]

        # Find indices for local maxima.
        max_indices = np.array([
            i for i in range(1, len(intensities) - 1)
            if intensities[i] > intensities[i - 1] and
            intensities[i] > intensities[i + 1]
        ], dtype=int)

        if len(max_indices) == 0:
            return (np.nan, np.nan)

        # Pick the local maximum with the highest intensity.
        max_idx = max_indices[np.argmax(intensities[max_indices])]

        # Determine observed retention time and signal-to-noise.
        time_observed = times[max_idx]
        try:
            sn = max(0.0, (intensities[max_idx] - background) / noise)
        except ZeroDivisionError:
            sn = np.nan

        return(time_observed, sn)
