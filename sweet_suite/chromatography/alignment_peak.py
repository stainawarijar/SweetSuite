import logging

import numpy as np


class AlignmentPeak:
    """Represents a specified alignment peak in LC-FLD data.

    Attributes:
        peak (str): Peak name as a string.
        time (float): The expected/required retention time in minutes.
        time_window (float): The time window in minutes around the expected 
            retention time in which to search for the peak.
        sn_cutoff (float): The minimum signal-to-noise that the peak should
            have to actually be used for alignment.
        required (bool): Indicates whether the peak is strictly required for
            alignment. If `True`, the alignment of the corresponding 
            chromatogram will fail if the S/N if below the cut-off.
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
        
        Args:
            peak: Peak name as a string.
            time: The expected/required retention time in minutes.
            time_window: The time window in minutes around the expected 
                retention time in which to search for the peak.
            sn_cutoff: The minimum signal-to-noise that the peak should have
                to actually be used for alignment.
            required: Indicates whether the peak is strictly required for
                alignment. If `True`, the alignment of the corresponding 
                chromatogram will fail if the S/N if below the cut-off.
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
            be found, `(np.nan, np.nan)` is returned. If noise is zero or 
            non-finite, `np.nan` is returned for the S/N value.
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
        # TODO: Proper error/warning message
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
            # TODO: Propper error/warning message
            return (np.nan, np.nan)

        # Pick the local maximum with the highest intensity.
        max_idx = max_indices[np.argmax(intensities[max_indices])]

        # Determine observed retention time and signal-to-noise.
        time_observed = times[max_idx]
        if noise == 0 or not np.isfinite(noise):
            self.logger.warning(
                f"Zero or non-finite noise value for peak {self.peak}."
            )
            sn = np.nan
        else:
            sn = max(0.0, (intensities[max_idx] - background) / noise)
    
        return(time_observed, sn)
