import numpy as np


def calibration_fit(
    calibrants: list[dict],
    include_time: bool = False # Temporary argument for testing
):
    """
    """
    mzs_observed = np.array([cal["mz_observed"] for cal in calibrants])
    mzs_exact = np.array([cal["mz_exact"] for cal in calibrants])

    if not include_time:
        # Classic second-degree polynomial fit:
        # mz_exact = b0 + b1 * mz_observed + b2 * mz_observed**2
        fit = np.polyfit(x = mzs_observed, y=mzs_exact, deg=2)
        return fit
    
    # TODO: Code here for a fit including time
    times = np.array([cal["time"] for cal in calibrants])

    # Center predictors to improve numerical stability
    mz_center = float(np.mean(mzs_observed))
    time_center = float(np.mean(time_center))

    x = mzs_observed - mz_center
    t = times - time_center

    # Additive model:
    # mz_exact = b0 + b1*x + b2*x**2 + b3*t

    design_matrix = np.column_stack([
        np.ones_like(x),
        x, x**2, t
    ])

    coefficients, residuals, rank, singular_values = np.linalg.lstsq(
        design_matrix, mzs_exact, rcond=None
    )

    if rank < design_matrix.shape[1]:
        raise ValueError(
            "The calibration model is rank deficient. "
            "More calibrants or better m/z and RT coverage are required."
        )

    return {
        "coefficients": coefficients,
        "mz_center": mz_center,
        "time_center": time_center,
        "residuals": residuals,
        "rank": rank,
        "singular_values": singular_values
    }
