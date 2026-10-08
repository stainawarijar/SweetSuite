import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px

from .chromatogram import Chromatogram


class FldChromatogram(Chromatogram):
    """Represents and HPLC-FLD chromatogram.
    
    Attributes:
        peak_width (float): ...
        data_baseline_corrected (np.ndarray | None): ...
        n_snip_iterations (int): ...
    """

    def __init__(
        self,
        data: np.ndarray,
        start_time: float = -np.inf,
        end_time: float = +np.inf,
        peak_width: float = 1.0
    ):
        """
        Args:
            data: Array of shape (N, 2) with time in column 0 and intensity
                in column 1, ordered from low to high time.
            start_time: Start of the retention time region of interest in
                minutes. Use `-np.inf` when not applicable.
            end_time: End of the retention time region of interest in 
                minutes. Use `np.inf` when not applicable.
            peak_width: Typical width of a chromatographic peak. This value
                is used to determine the number of SNIP iterations during
                baseline correction. A generous value should be used, because
                an underestimation can result in subtracting real signal (see
                https://cremerlab.github.io/hplc-py/methodology/baseline.html).
        """
        super().__init__(data, start_time, end_time)
        self.peak_width = peak_width

        @property
        def n_snip_iterations(self) -> int:
            """Determine the number of SNIP iterations to use for baseline
            correction, based on the set peak width setting.
            """
            dt = np.median(np.diff(self.data_roi[:, 0]))
            window_points = int(round(self.peak_width / dt))

            # Prefer an odd window size
            if window_points % 2 == 0:
                window_points += 1

            return (window_points - 1) // 2

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
                filtered = FldChromatogram.snip_iteration(filtered, m)

            return filtered

        @property
        def data_baseline_corrected(self) -> np.ndarray:
            """Applies baseline correction to the chromatogram data in the 
            retention time region of interest, using the SNIP algorithm.

            Returns:
                A 2D array containing the baseline-corrected chromatogram data
                in the retention time region of interest.
            """
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
            filtered_lss = FldChromatogram.snip_filter(
                signal=signal_lss, 
                n_iterations=self.n_snip_iterations
            )
    
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

        @property
        def data_for_background_and_noise(self):
            """Prefer baseline-corrected data when available.
            
            This overwrites the `data_for_background_and_noise` of the
            `Chromatoram` parent class, which defaults to `data_roi`.
            """
            if self.data_baseline_corrected is not None:
                return self.data_baseline_corrected
            return self.data_roi

        def plotly(self):
            """Create an interactive Plotly figure of the chromatographic data
            in the retention time region of interest.
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

        def plotly_baseline_corrected(self):
            """Create an interactive Plotly figure of the baseline corrected
            chromatographic data in the retention time region of interest.
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
