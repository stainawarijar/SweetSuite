import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px


class Chromatogram:
    """Represents a chromatogram.

    Attributes:
        data (np.ndarray): Chromatogram as an array of shape (N, 2) where
            column 0 is time and column 1 is intensity.
        start_time (float): ...
        end_time (float): ...
        data_roi (np.ndarray): Chromatogram data within the current retention
            time region of interest.
        data_baseline_corrected (np.ndarray | None): ...
    """

    def __init__(
        self,
        data: np.ndarray,
        start_time: float = -np.inf,
        end_time: float = +np.inf,
        baseline_peak_width: float = 1.0
    ):
        """Initialize a chromatogram.

        Args:
            data: ...
            start_time: ...
            end_time: ...
        """
        self.data = data
        self.start_time = start_time
        self.end_time = end_time
        self.baseline_peak_width = baseline_peak_width
        self.data_baseline_corrected = None

    @property
    def data_roi(self) -> np.ndarray:
        """Return chromatogram data in retention time region of interest."""
        rt = self.data[:, 0]
        mask = (rt >= self.start_time) & (rt <= self.end_time)

        return self.data[mask]

    @staticmethod
    def snip_iteration(signal, m):
        """Apply one SNIP minimum-filter iteration.

        Args:
            signal: One-dimensional LLS-transformed signal.
            m: Distance in data points to the comparison points.
        
        Returns:
            Signal after one SNIP iteration.
        """
        filtered = signal.copy()

        for i in range(m, len(signal) - m):
            boundary_mean = (signal[i - m] + signal[i + m]) / 2
            filtered[i] = min(signal[i], boundary_mean)

        return filtered

    @staticmethod
    def snip_filter(signal, n_iterations):
        """Apply iterative SNIP filtering.
        
        Args:
            signal: One-dimensional LLS-transformed signal.
            n_iterations: Number of SNIP iterations.
        
        Returns:
            SNIP-filtered signal.
        """
        filtered = signal.copy()

        for m in range(1, n_iterations + 1):
            filtered = Chromatogram.snip_iteration(filtered, m)

        return filtered

    def n_snip_iterations(self) -> int:
        """Determine the number of SNIP iterations to use for baseline
        correction, based on the set peak width setting.
        """
        dt = np.median(np.diff(self.data_roi[:, 0]))
        window_points = int(round(self.baseline_peak_width / dt))

        # Prefer an odd window size
        if window_points % 2 == 0:
            window_points += 1

        return (window_points - 1) // 2

    def correct_baseline(self) -> None:
        """Applies baseline correction to the chromatogram data in the 
        retention time region of interest, using the SNIP algorithm."""
        rt_roi = self.data_roi[:, 0]
        signal_roi = self.data_roi[:, 1]

        # Shift intensities so all values are non-negative.
        offset = max(0.0, -signal_roi.min())
        signal_shifted = signal_roi + offset

        # Apply log-log-square-root (LSS) transformation.
        # This compresses the intensity range, preventing large peaks from
        # dominating the filtering and small peaks from being erased.
        signal_lss = np.log(
            np.log(
                np.sqrt(signal_shifted + 1) + 1
            ) + 1
        )

        # SNIP iterations filter peaks out of the LSS-transformed data, so that
        # only the LSS_transformed baseline remains.
        n_iterations = self.n_snip_iterations()
        filtered_lss = Chromatogram.snip_filter(signal_lss, n_iterations)

        # Apply inverse LSS to the LSS-transformed baseline, so we get an 
        # estimate for the baseline in the shifted data.
        baseline_shifted = (
            np.exp(
                np.exp(filtered_lss) - 1
            ) - 1
        ) ** 2 - 1

        # Subtract offset from estimated baseline.
        # Store as attribute for plotting.
        baseline = baseline_shifted - offset

        # Subtract baseline from original signal.
        signal_corrected = signal_roi - baseline

        # Update attribute.
        self.data_baseline_corrected = np.column_stack((
            rt_roi, signal_corrected
        ))

    def get_background_and_noise(self) -> tuple[float, float]:
        """Estimates the chromatographic background and noise.

        When available, the baseline-corrected chromatographic trace is used.
        Otherwise the raw trace is used in the time region of interest.

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
        # Determine whether to use baseline-corrected or raw trace.
        if self.data_baseline_corrected is not None:
            data = self.data_baseline_corrected
        else:
            data = self.data_roi

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

    def plot_interactive(self):
        """Create an interactive Plotly figure of the chromatogram in the
        retention time region of interest.
        """
        fig = px.line(
            x=self.data_roi[:, 0],
            y=self.data_roi[:, 1]
        )

        fig.update_traces(
            line=dict(color="black"),
            name="Original signal",
            showlegend=True
        )

        fig.update_layout(
            template="simple_white",
            xaxis_title="Retention time (min)",
            yaxis_title="Intensity"
        )

        return fig

    def plot_baseline_corrected(self):
        """
        """
        if self.data_baseline_corrected is None:
            return

        rt_roi = self.data_roi[:, 0]
        signal_roi = self.data_roi[:, 1]
        signal_corrected = self.data_baseline_corrected[:, 1]

        # Start with figure containing raw chromatogram trace.
        fig = self.plot_interactive()

        # Determine original baseline.
        baseline = signal_roi - signal_corrected

        # Add baseline and corrected signal to figure.
        fig.add_scatter(
            x=rt_roi,
            y=baseline,
            mode="lines",
            name="Original baseline",
            line=dict(color="red")
        )

        fig.add_scatter(
            x=rt_roi,
            y=signal_corrected,
            mode="lines",
            name="Baseline-corrected signal",
            line=dict(color="blue")
        )

        return fig