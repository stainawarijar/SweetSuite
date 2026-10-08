import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px


class Chromatogram:
    """Represents a chromatogram.

    Attributes:
        data (np.ndarray): Chromatogram as an array of shape (N, 2) where
            column 0 is time and column 1 is intensity.
        start_time (float): Start of the retention time region of interest in
            minutes. Use `-np.inf` when not applicable.
        end_time (float): End of the retention time region of interest in 
            minutes. Use `np.inf` when not applicable.
        data_roi (np.ndarray): Chromatogram data in the retention time region
            of interest, as specified by `start_time` and `end_time`.
        data_for_background_and_noise (np.ndarray): The chromatographic data
            used for background and noise determination.
        background_and_noise (tuple[float, float]): (background, noise) where
            background is the mean and noise is the standard deviation of the
            background region.
    """

    def __init__(
        self,
        data: np.ndarray,
        start_time: float = -np.inf,
        end_time: float = +np.inf
    ):
        """Initialize a chromatogram.

        Args:
            data: Chromatogram as an array of shape (N, 2) where column 0 is 
                time and column 1 is intensity.
            start_time: Start of the retention time region of interest in
                minutes. Use `-np.inf` when not applicable.
            end_time: End of the retention time region of interest in 
                minutes. Use `np.inf` when not applicable.
        """
        self.data = data
        self.start_time = start_time
        self.end_time = end_time

    @property
    def data_roi(self) -> np.ndarray:
        """Return chromatogram data in retention time region of interest."""
        rt = self.data[:, 0]
        mask = (rt >= self.start_time) & (rt <= self.end_time)
        
        return self.data[mask]

    @property
    def data_for_background_and_noise(self):
        """Return the data used for background and noise estimation.
        
        `data_roi` is used here by default, but in `FldChromatogram` (a child
        class of `Chromatogram`) this is overwritten by the baseline-corrected 
        chromatogram data.
        """
        return self.data_roi

    @property
    def background_and_noise(self) -> tuple[float, float]:
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
        data = self.data_for_background_and_noise

        # Sort the intensities from low to high.
        intensities = np.sort(data[:, 1])

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
