import numpy as np
import matplotlib.pyplot as plt


class Eic:
    """Represents an extracted ion chromatogram (EIC).

    This class holds the raw chromatographic trace for a single m/z value.

    Attributes:
        mz_exact (float): Target mass-to-charge ratio for this chromatogram.
        data (np.ndarray): Chromatogram as an array of shape (N, 2) where
            column 0 is time and column 1 is intensity.
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
        maximum (tuple[float, float]): (time, intensity) at the maximum within
            the peak window.
        background_and_noise (tuple[float, float]): (background, noise) where
            background is the mean and noise is the standard deviation of the
            final background region.
        signal_to_noise (float): Signal-to-noise ratio computed as
            `(max_intensity - background) / noise`.
    """
    
    def __init__(
            self,
            mz_exact: float,
            data: np.ndarray,
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
        self.data = data
        self.mz_exact = mz_exact
        self.time_required = time_required
        self.alignment_time_window = alignment_time_window
        self.alignment_sn_cutoff = alignment_sn_cutoff
        self.required_for_alignment = required_for_alignment
        self.peak_data = self.get_peak_data()
        self.maximum = self.get_maximum()
        self.background_and_noise = self.get_background_and_noise()
        self.signal_to_noise = self.get_signal_to_noise()
    
    def get_peak_data(self) -> np.ndarray:
        """Returns a subset of the chromatographic run with only those
        retention times that are inside the specified alignment rime range."""
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

    def get_maximum(self) -> tuple[float, float]:
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
    
    def get_background_and_noise(self) -> tuple[float, float]:
        """Estimates the chromatographic background and noise.

        This method sorts the intensity values in ascending order and selects 
        the lowest ~25% of the data points as an initial region. It then 
        iteratively adjusts this region by either growing it (if the next point 
        is within 3 standard deviations of the region's mean) or shrinking it 
        (if the next point is outside this boundary) to identify a stable 
        background region. The final region's mean is taken as the background, 
        and its standard deviation as the noise.

        Returns:
            A tuple containing the estimated background and noise.
        """
        # Sort the intensities from low to high.
        intensities = np.sort(self.data[:, 1])

        # Determine total number of data points.
        n = intensities.shape[0]
        
        # Take lowest ~25% of data points as initial region.
        size = round(n / 4) 

        # Explictly deal with small initial size.
        # Need at least 3 initial data points (n >= 11) to be able to shrink
        # the region and then still calculate average and SD.
        # NOTE: Should not occur if the entire chromatographic run is used.
        if size < 3:
            return (np.nan, np.nan)

        # Calculate average and SD of initial region.
        region = intensities[:size]
        avg = np.average(region)
        sd = np.std(region, ddof=1)

        # Scenario 1: First data point outside current region falls inside
        # the (average + 3*SD) boundary. Grow the region until this is no
        # longer the case, or until all data points are included.
        if intensities[size] <= (avg + 3 * sd):
            while intensities[size] <= (avg + 3 * sd):
                size += 1
                region = intensities[:size]
                if size == n:
                    break
                avg = np.average(region)
                sd = np.std(region, ddof=1)
            # Remove last added data point, unless all were used.
            if size < n:
                region = region[:-1]
        
        # Scenario 2: First data point outside current region is above the
        # (average + 3*SD) boundary. Shrink the region until this is not the
        # case, or until we are left with only 2 data points.
        else:
            while intensities[size] > (avg + 3 * sd):
                size -= 1
                region = intensities[:size]
                if size == 2:
                    break
                avg = np.average(region)
                sd = np.std(region, ddof=1)
            # Add back the last removed data point, unless size == 2.
            if size > 2:
                region = intensities[:size + 1]
    
        # Get average and SD of final data as background and noise.
        background = np.average(region)
        noise = np.std(region, ddof=1)

        return (background, noise)

    def get_signal_to_noise(self) -> float:
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
            return float(0)
    
    def plot_unaligned(self, range: str):
        """Plots the unaligned extracted ion chromatogram.

        Vertical blue lines are used to mark the alignment retention time 
        range. The observed and required retention times are marked by red
        and green vertical lines, respectively.

        Args: 
            range: 'peak' to only plot the alignment retention time range,
                'full' to plot the entire chromatographic run.
        """
        # Select required data.
        if range == "peak":
            x = self.peak_data[:, 0]
            y = self.peak_data[:, 1]
        elif range == "full":
            x = self.data[:, 0]
            y = self.data[:, 1]

        # Create figure and axes.
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot(x, y, linestyle="-", color="black")
        ax.axvline(x=self.time_required - self.alignment_time_window, color="blue")
        ax.axvline(x=self.time_required + self.alignment_time_window, color="blue")
        ax.axvline(x=self.time_required, color="green", label="target")
        ax.axvline(x=self.maximum[0], color="red", label="observed")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Intensity")
        ax.set_title(f"EIC for {self.mz_exact} Th")
        ax.legend(loc="best")

        return fig