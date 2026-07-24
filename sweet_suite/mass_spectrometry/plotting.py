from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.ticker import ScalarFormatter
import numpy as np


def plot_polynomial(
    mzs_observed: list[float],
    mzs_exact: list[float],
    poly_func: np.poly1d,
    title: str
) -> Figure:
    """Plots a polynomial calibration curve for mass spectrometry data.

    This function creates a side-by-side visualization with a calibration plot 
    on the left and a summary table on the right. The plot shows observed m/z 
    values against exact m/z values before and after polynomial calibration, 
    along with the polynomial fit curve and a reference line representing 
    perfect calibration.
    
    The table displays pre- and post-calibration mass errors (in ppm) for each 
    calibrant, sorted by m/z from high to low. Post-calibration errors are 
    color-coded: dark green when calibration improved the mass error, dark red 
    when it worsened. Figure height scales dynamically with the number of 
    calibrants to ensure readability.

    Args:
        mzs_observed: List of observed m/z values from mass spectrometry.
        mzs_exact: List of exact (theoretical) m/z values.
        poly_func: Polynomial function used for calibration (degree 2).
        title: Title for the plot.

    Returns:
        Matplotlib Figure object containing the calibration plot and table
        in a side-by-side layout.
    """
    # Unrounded and rounded polynomial coefficients.
    a, b, c = poly_func[0], poly_func[1], poly_func[2]
    ar, br, cr = np.round(a, 3), np.round(b, 3), np.round(c, 3)
    sign_b = "-" if b < 0 else "+"
    sign_c = "-" if c < 0 else "+"
    
    # Function to show in plot.
    function = fr"Fit: $y = {ar}x^{{{2}}} {sign_b} {abs(br)}x {sign_c} {abs(cr)}$"
    x_fit = np.linspace(np.min(mzs_observed), np.max(mzs_observed), 100) 
    y_fit = poly_func(x_fit)

    # Apply polynomial to observed m/z values.
    mz_array = np.array(mzs_observed)
    mzs_adjusted = poly_func(mz_array)

    # Calculate pre- and post-calibration mass errors (ppm).
    mzs_exact_array = np.array(mzs_exact)
    pre_cal_errors = (mz_array - mzs_exact_array) / mzs_exact_array * 1e6
    post_cal_errors = (mzs_adjusted - mzs_exact_array) / mzs_exact_array * 1e6

    # Sort data by m/z (high to low) for table.
    sort_indices = np.argsort(mzs_exact_array)[::-1]
    
    # Create figure with gridspec for side-by-side layout.
    # Scale height based on number of calibrants to accommodate table.
    num_calibrants = len(mzs_observed)
    fig_height = max(6, min(10, 4 + num_calibrants * 0.25))
    fig = plt.figure(figsize=(12, fig_height))
    gs = gridspec.GridSpec(1, 2, width_ratios=[2.5, 1], figure=fig)
    
    # Create plot on the left.
    ax_plot = fig.add_subplot(gs[0])
    ax_plot.scatter(
        mzs_observed, mzs_exact, label="Uncalibrated",
        color="#FF851B", alpha=0.5, s=80
    )
    ax_plot.scatter(
        mzs_adjusted, mzs_exact, label="Calibrated",
        color="#0074D9", alpha=0.5, marker="s", s=80
    )
    ax_plot.plot(x_fit, y_fit, color="#FF851B", label=function)
    ax_plot.plot(x_fit, x_fit, color="#0074D9", linestyle="--", label="Target")
    ax_plot.set_xlabel("Observed m/z")
    ax_plot.set_ylabel("Exact m/z")
    ax_plot.set_title(title)
    
    # Disable scientific notation on both axes
    ax_plot.xaxis.set_major_formatter(ScalarFormatter(useOffset=False))
    ax_plot.yaxis.set_major_formatter(ScalarFormatter(useOffset=False))
    ax_plot.ticklabel_format(style='plain', axis='both')
    
    ax_plot.legend(loc="upper left")

    # Create table on the right.
    ax_table = fig.add_subplot(gs[1])
    ax_table.axis('off')
    
    # Prepare table data (sorted high to low).
    table_data = []
    for idx in sort_indices:
        table_data.append([
            f"{mzs_exact[idx]:.4f}",
            f"{pre_cal_errors[idx]:.2f}",
            f"{post_cal_errors[idx]:.2f}"
        ])
    
    # Create table.
    table = ax_table.table(
        cellText=table_data,
        colLabels=["Exact m/z", "Pre-cal. ppm", "Post-cal. ppm"],
        loc="center",
        cellLoc="center",
        colWidths=[0.35, 0.325, 0.325]
    )
    
    # Style the table.
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.8)
    
    # Style header row.
    for i in range(3):
        cell = table[(0, i)]
        cell.set_facecolor('#E8E8E8')
        cell.set_text_props(weight='bold')
    
    # Color-code post-calibration errors.
    for row_idx, idx in enumerate(sort_indices):
        # row_idx + 1 because row 0 is the header
        post_cal_cell = table[(row_idx + 1, 2)]
        pre_cal_abs = abs(pre_cal_errors[idx])
        post_cal_abs = abs(post_cal_errors[idx])
        
        if post_cal_abs < pre_cal_abs:
            # Improved - dark green
            post_cal_cell.set_text_props(color='darkgreen', weight='bold')
        else:
            # Worsened - dark red
            post_cal_cell.set_text_props(color='darkred', weight='bold')
    
    plt.tight_layout()
    
    return fig

