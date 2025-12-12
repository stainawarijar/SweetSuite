from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import curve_fit

from .eic import Eic


def fit_power(
        eics: list[Eic],
        min_peaks: int
) -> np.ndarray | None:
    """Fit a power function through a list of (observed, required) retention
    time pairs.

    This function creates pairs of (observed, required) retention times for
    EICs that were created for alignment features. The required retention
    times are then fitted as a function of the observed retention times using
    a power function (Y = a*X^b + c). If that fails, a linear fit is used
    (Y = a*X + b).

    Args:
        eics: A list with instances of `Eic`, for each alignment feature.
        min_peaks: Minimum number of peaks to use for alignment.
    
    Returns:
        An array containing coefficients of the fit. For a quadratic fit, 
        it takes the form [a, b, c] for Y = a*X^b + C.
        For a linear fit, it takes on the form [a, b] for Y = a*X + b.
        `None` if minimum number of peaks is not met, or if fitting failed
        for some other reason.
    """
    # Check if enough for fitting
    if len(eics) < min_peaks:
        return
    
    # Prepare for fitting.
    times_observed = np.array([eic.maximum[0] for eic in eics])
    times_required = np.array([eic.time_required for eic in eics])

    def func_power(x, a, b, c):
        if b > 2:
            penalty = abs(b - 1) * 10000
        elif b < 0:
            penalty = abs(2 - b) * 10000
        else:
            penalty = 0
        
        return a*(x**b) + c + penalty

    def func_linear(x, a, b):
        return a*x + b
    
    # Fit powerquadratic function. If it fails, fall back to linear fit.
    # If that also fails, set to `None`.
    try:
        fit = curve_fit(func_power, times_observed, times_required)
    except RuntimeError:
        try:
            fit = curve_fit(func_linear, times_observed, times_required)
        except RuntimeError:
            fit = None
    
    # Return the coefficients.
    return fit[0]


def plot_fit(
        times_observed: list[float],
        times_required: list[float],
        fit_coeffs: np.ndarray,
        title: str
) -> Figure:
    """Visualize the curve fitting for retention alignment.
    
    This function plots the (observed, required) retention time pairs
    for all features that were used for alignment, using red points.
    The power/linear fit is plotted through the data points. 
    The (adjusted, required) retention time pairs of the features are 
    plotted using blue squares. A blue dotted line is used to indicate
    the target. The closer the blue squares are to the target line, the
    more accurate the retention time alignment.

    Args:
        times_observed: A list with observed retention times for each 
            alignment feature.
        times_required: A list with required retention times for each
            alignment feature.
        fit_coeffs: An array with fit coefficients ([a, b, c] or [a, b]).
        title: Title for the plot.
    
    Returns:
        A matplotlib figure.
    """
    x_fit = np.linspace(np.min(times_observed), np.max(times_observed), 100)  

    if len(fit_coeffs) == 3:
        a, b, c = fit_coeffs[0], fit_coeffs[1], fit_coeffs[2]
        ar, br, cr = np.round(a, 2), np.round(b, 2), np.round(c, 2)
        function = fr"Power fit: $y = {ar}x^{{{br}}} + {cr}$"
        times_adjusted = a * times_observed**b + c
        y_fit = a * x_fit **b + c
    else:
        a, b = fit_coeffs[0], fit_coeffs[1]
        ar, br = np.round(a, 2), np.round(b, 2)
        function = fr"Linear fit: $y = {ar}x + {br}$"
        times_adjusted = a * times_observed + b
        y_fit = a * x_fit + b
    
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(
        times_observed, times_required, label="Unaligned",
        color="red", alpha=0.7
    )
    ax.scatter(
        times_adjusted, times_required, label="Aligned",
        color="blue", alpha=0.7, marker="s"
    )
    ax.plot(x_fit, y_fit, color="red", label=function)
    ax.plot(x_fit, x_fit, color="blue", linestyle="--", label="Target")
    ax.set_xlabel("Observed retention time (seconds)")
    ax.set_ylabel("Required retention time (seconds)")
    ax.set_title(title)
    ax.legend(loc="best")

    return fig

