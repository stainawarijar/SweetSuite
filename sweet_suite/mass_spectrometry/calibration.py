from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import numpy as np


def fit_calibration(
    calibrants: list[dict] | None,
    include_time: bool = False
) -> np.ndarray:
    """Fit an m/z calibration model using specified calibrants.

    The model predicts the required m/z correction

        `mz_exact - mz_observed`
    
    as a quadratic function of the observed m/z. If `inlude_time` is `True`,
    a linear retention time term is included in the model.

    Args:
        calibrants: A list containing calibrants, where each calibrant is
            specified as a dictionary containing `mz_exact`, `mz_observed`,
            `time` and `time_window`. For MS-only data, `time` and `time_window`
            will be `None` and calibration is performed only on m/z.
        include_time: Whether to include a retention time term in the fitted
            calibration model. Should always be `False` for MS-only data.
    
    Returns:
        An array containing the model coefficients.
        - If time is not included: [quadratic m/z, linear m/z, intercept]
        - If time is included: [quadratic m/z, linear m/z, time, intercept]

        If `calibrants` is `None` or an empty list, `None` is returned.
    """
    if calibrants is None or len(calibrants) == 0:
        return None

    mz_observed = np.array(
        [cal["mz_observed"] for cal in calibrants],
        dtype=float
    )

    mz_delta = np.array(
        [cal["mz_exact"] - cal["mz_observed"] for cal in calibrants],
        dtype=float
    )

    if not include_time:
        return np.polyfit(x=mz_observed, y=mz_delta, deg=2)

    time = np.array(
        [cal["time"] for cal in calibrants],
        dtype=float
    )

    design_matrix = np.column_stack(
        [
            mz_observed**2,
            mz_observed,
            time,
            np.ones_like(mz_observed)
        ]
    )

    fit, _, _, _ = np.linalg.lstsq(design_matrix, mz_delta, rcond=None)

    return fit


def plot_quadratic_calibration(
    calibrants: list[dict],
    fit: np.ndarray | None,
    title: str = ""
) -> Figure | None:
    """Plot the local quadratic m/z calibration fit.

    Required m/z corrections are plotted against the observed m/z values.
    Calibrant data points are colored by their retention time if applicable.
    The quadratic fit is shown as a smooth curve.

    Args:
        calibrants: A list containing calibrants, where each calibrant is
            specified as a dictionary containing `mz_exact`, `mz_observed`,
            `time` and `time_window`. For MS-only data, `time` and `time_window`
            will be `None` and data points are not colored by retention time.
        fit: Array containing the quadratic m/z fit coefficients in 
            descending order: [quadratic, linear, intercept].
        title: Title to place above the figure.
    
    Returns:
        A matplotlib Figure. If `"fit"` is `None` or does not contain three
        coefficients, `None` is returned.
    """
    if fit is None or len(fit) != 3:
        return None
    
    mz_observed = np.array(
        [cal["mz_observed"] for cal in calibrants],
        dtype=float
    )
    
    mz_delta = np.array(
        [cal["mz_exact"] - cal["mz_observed"] for cal in calibrants],
        dtype=float
    )

    time = np.array(
        [cal["time"] for cal in calibrants],
        dtype=float
    )

    if np.isnan(time).any():
        color_by_time = False
    else:
        color_by_time = True

    # Create evenly spaced m/z values for drawing smooth fitted curve.
    mz_plot = np.linspace(mz_observed.min(), mz_observed.max(), 500)

    # Apply the fit to the specified m/z values.
    delta_fitted = np.polyval(fit, mz_plot)

    # Create figure
    figure, axis = plt.subplots()
    if color_by_time:
        scatter = axis.scatter(
            mz_observed,
            mz_delta,
            c=time,
            cmap="brg",
            s=45,
            edgecolor="black",
            linewidths=0.4
        )
    else:
        scatter = axis.scatter(
            mz_observed,
            mz_delta,
            c="blue",
            s=45,
            edgecolor="black",
            linewidths=0.4
        )
    axis.plot(
        mz_plot,
        delta_fitted,
        label="Quadratic fit"
    )
    axis.axhline(0, linewidth=1, linestyle="--", c="black")
    axis.set_xlabel(r"Observed $m/z$")
    axis.set_ylabel(r"Required correction $\Delta m/z$")
    axis.set_title(title)
    axis.legend()
    if color_by_time:
        colorbar = figure.colorbar(scatter, ax=axis)
        colorbar.set_label("Sum spectrum retention time")
    figure.tight_layout()

    return figure
