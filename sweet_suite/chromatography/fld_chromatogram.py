import logging

from matplotlib.figure import Figure
import numpy as np
from numpy.polynomial import Polynomial
import plotly.express as px

from .alignment import rt_fit_quadratic
from .alignment_peak import AlignmentPeak
from .chromatogram import Chromatogram


class FldChromatogram(Chromatogram):
    """Represents and HPLC-FLD chromatogram.
    
    Attributes:
        peak_width (float): ...
        data_baseline_corrected (np.ndarray | None): ...
        alignment_peaks (list[AlignmentPeak] | None): ...
    """

    def __init__(
        self,
        name: str,
        data: np.ndarray,
        start_time: float = -np.inf,
        end_time: float = +np.inf,
        peak_width: float = 1.0,
        alignment_peaks: list[AlignmentPeak] | None = None
    ):
        """
        Args:
            name: Name of the chromatogram.
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
            alignment_peaks: An optional list containing instanced of `AlignmentPeak`.
                Only required when performing retention time alignment.
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.data_baseline_corrected = None
        self.peak_width = peak_width
        self.alignment_peaks = alignment_peaks
        self.name = name
        super().__init__(data, start_time, end_time)

    @staticmethod
    def parse_number(value):
        """Helper function used to ensure that decimals are denoted
        using dots rather than commas.
        """
        value = value.strip()
        # A comma marks European formatting: 1.259,25 -> 1259.25.
        # Without a comma, retain the dot as the decimal separator.
        if "," in value:
            value = value.replace(".", "").replace(",", ".")
        return float(value)

    def get_n_snip_iterations(self) -> int:
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

    def correct_baseline(self) -> None:
        """Applies baseline correction to the chromatogram data in the 
        retention time region of interest, using the SNIP algorithm.

        Returns:
            `None`. The attribute `self.data_baseline_corrected` is updated 
            with a 2D array containing the baseline-corrected chromatogram 
            data in the retention time region of interest.
        """
        n_snip_iterations = self.get_n_snip_iterations()

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
            n_iterations=n_snip_iterations
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
        self.data_for_background_and_noise = self.get_data_for_background_and_noise()
        self.background_and_noise = self.get_background_and_noise()

    def get_data_for_background_and_noise(self):
        """Prefer baseline-corrected data when available.
        
        This overwrites the `data_for_background_and_noise` of the
        `Chromatgram` parent class, which defaults to `data_roi`.
        """
        if self.data_baseline_corrected is not None:
            return self.data_baseline_corrected
        return self.data_roi

    def get_alignment_fit(
        self, 
        min_peaks: int = 4
    ) -> tuple[Polynomial, Figure]:
        """Perform retention time alignment fit on the chromatogram data in the
        retention time region of interest.

        If baseline correction was performed, the baseline corrected data
        is used. Otherwise the uncorrected data is used.

        Args:
            min_peaks: The minimum number of peaks required for alignment.
                Defaults to 4, which is the absolute minimum required for 
                a quadratic fit.

        Returns:
            A tuple containing a NumPy Polynomial fit object as its first 
            element and a matplotlib figure as its second element.
        """
        if self.alignment_peaks is None or len(self.alignment_peaks) == 0:
            return

        if self.data_baseline_corrected is not None:
            data = self.data_baseline_corrected
        else:
            data = self.data_roi

        # Collect alignment peak data with high enough S/N.
        alignment_data = []
        
        for peak in self.alignment_peaks:
            info = peak.get_info(
                data=data,
                background=self.background_and_noise[0],
                noise=self.background_and_noise[1]
            )
            time_observed = info[0]
            sn = info[1]

            if not (np.isfinite(time_observed) and np.isfinite(sn)):
                if peak.required:
                    # Mising required peak -> fail alignment.
                    # TODO: Create figure for missing required peak.
                    missing_required_fig = None
                    return (None, missing_required_fig)
                else:
                    # TODO: Log a message.
                    continue

            if sn >= peak.alignment_sn_cutoff:
                alignment_data.append((time_observed, peak.time_required))
            elif peak.required:
                # Mising required peak -> fail alignment.
                # TODO: Create figure for missing required peak.
                missing_required_fig = None
                return (None, missing_required_fig)

        # Check if there are enough data points for fitting.
        if len(alignment_data) < min_peaks:
            # TODO: Proper warning message.
            # TODO: Replace second `None` by a failed alignment figure.
            failed_fig = None
            return (None, failed_fig)

        # Get quadratic alignment fit.
        fit = rt_fit_quadratic(
            points=alignment_data, 
            units="min", 
            title=self.name
        )

        return fit

    def get_aligned_data(
        self,
        poly: Polynomial | None
    ) -> np.ndarray | None:
        """Apply a polynomial correction to the retention times in the 
        chromatogram data to get aligned data. 

        The correction is applied only to the data in the region of interest.

        Args:
            poly: A NumPy Polynomial object that predicts the required
            retention time correction.
        
        Returns:
            A 2D array with aligned retention times in the first column and
            intensities in the second column. `None` when the corrected 
            retention times include non-finite values or when the corrected
            times are not strictly increasing.
        """
        intensities = self.data_roi[:, 1]
        times_observed = self.data_roi[:, 0]
        times_aligned = times_observed + poly(times_observed)

        if not np.isfinite(times_aligned).all():
            self.logger.warning(
                f"Alignment rejected for {self.name}: non-finite corrected retention times"
            )
            return
        
        if not np.all(times_aligned[1:] > times_aligned[:-1]):
            self.logger.warning(
                f"Alignment rejected for {self.name}: corrected times are not strictly increasing"
            )
            return
        
        return np.column_stack((times_aligned, intensities))

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
        fig = self.plotly()

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
