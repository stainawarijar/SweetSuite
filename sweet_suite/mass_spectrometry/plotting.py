from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import numpy as np


def plot_polynomial(
        mzs_observed: list[float],
        mzs_exact: list[float],
        poly_func: np.poly1d,
        title: str
) -> Figure:
    """Plots a polynomial calibration curve for mass spectrometry data.

    This function creates a scatter plot comparing observed m/z values against
    exact m/z values before and after polynomial calibration. It also displays
    the polynomial fit curve and a reference line representing perfect calibration.

    Args:
        mzs_observed: List of observed m/z values from mass spectrometry.
        mzs_exact: List of exact (theoretical) m/z values.
        poly_func: Polynomial function used for calibration (degree 2).
        title: Title for the plot.

    Returns:
        Matplotlib Figure object containing the calibration plot.
    """
    # Unrounded and rounded polynomial coefficients.
    a, b, c = poly_func[0], poly_func[1], poly_func[2]
    ar, br, cr = np.round(a, 3), np.round(b, 3), np.round(c, 3)
    
    # Function to show in plot.
    function = fr"Fit: $y = {ar}x^{{{2}}} + {br}x + {cr}$"
    x_fit = np.linspace(np.min(mzs_observed), np.max(mzs_observed), 100) 
    y_fit = poly_func(x_fit)

    # Apply polynomial to observed m/z values.
    mz_array = np.array(mzs_observed)
    mzs_adjusted = poly_func(mz_array)

    # Create figure.
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(
        mzs_observed, mzs_exact, label="Uncalibrated",
        color="#FF851B", alpha=0.5
    )
    ax.scatter(
        mzs_adjusted, mzs_exact, label="Calibrated",
        color="#0074D9", alpha=0.5, marker="s"
    )
    ax.plot(x_fit, y_fit, color="#FF851B", label=function)
    ax.plot(x_fit, x_fit, color="#0074D9", linestyle="--", label="Target")
    ax.set_xlabel("Observed m/z")
    ax.set_ylabel("Required m/z")
    ax.set_title(title)
    ax.legend(loc="best")

    return fig

