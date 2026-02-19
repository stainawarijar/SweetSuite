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
    
    # Function to show in plot.
    function = fr"Fit: $y = {ar}x^{{{2}}} + {br}x + {cr}$"
    x_fit = np.linspace(np.min(mzs_observed), np.max(mzs_observed), 100) 
    y_fit = poly_func(x_fit)

    # Apply polynomial to observed m/z values.
    mz_array = np.array(mzs_observed)
    mzs_adjusted = poly_func(mz_array)

    # Calculate pre- and post-calibration mass errors (ppm).
    mzs_exact_array = np.array(mzs_exact)
    pre_cal_errors = (mzs_exact_array - mz_array) / mzs_exact_array * 1e6
    post_cal_errors = (mzs_exact_array - mzs_adjusted) / mzs_exact_array * 1e6

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
            f"{mzs_exact[idx]:.2f}",
            f"{pre_cal_errors[idx]:.1f}",
            f"{post_cal_errors[idx]:.1f}"
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


def plot_calibration_failure(
        title: str,
        mzs_observed: list[float],
        mzs_exact: list[float]
) -> Figure:
    """Creates a plot showing calibration failure with diagnostic information.

    This function generates a figure matching the successful calibration layout
    but showing only uncalibrated data points and the target line in red,
    along with a table showing pre-calibration mass errors.

    Args:
        title: Title for the plot (mass spectrum name).
        mzs_observed: List of observed m/z values from mass spectrometry.
        mzs_exact: List of exact (theoretical) m/z values.

    Returns:
        Matplotlib Figure object containing the uncalibrated calibration plot
        with failure message and pre-calibration errors table.
    """
    # Convert to numpy arrays for calculations.
    mz_array = np.array(mzs_observed)
    mzs_exact_array = np.array(mzs_exact)
    
    # Check if there are any calibrants to display.
    has_calibrants = len(mzs_observed) > 0
    
    if has_calibrants:
        # Calculate pre-calibration mass errors (ppm).
        pre_cal_errors = (mzs_exact_array - mz_array) / mzs_exact_array * 1e6
        
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
    else:
        # No calibrants - single plot layout without table.
        fig = plt.figure(figsize=(8, 6))
        ax_plot = fig.add_subplot(1, 1, 1)
    
    # Handle case when there are calibrants to plot.
    if has_calibrants:
        # Plot only uncalibrated data points in red.
        ax_plot.scatter(
            mz_array, mzs_exact_array, label="Uncalibrated",
            color="#CC0000", alpha=0.5, s=80
        )
        
        # Plot target line in red.
        # For a single data point, use observed m/z ± 50
        min_mz = np.min(mz_array)
        max_mz = np.max(mz_array)
        
        # If there's only one point, expand the range by ±50 m/z
        if min_mz == max_mz:
            min_mz = min_mz - 50
            max_mz = max_mz + 50
        
        x_range = np.array([min_mz, max_mz])
        ax_plot.plot(x_range, x_range, color="#CC0000", linestyle="--", label="Target", linewidth=2)
        
        # Set equal axis limits to keep the diagonal nature of the target line clear
        ax_plot.set_xlim(min_mz, max_mz)
        ax_plot.set_ylim(min_mz, max_mz)
    else:
        # No calibrants passed S/N threshold - set default axis limits.
        ax_plot.set_xlim(0, 100)
        ax_plot.set_ylim(0, 100)
    
    # Add failure message to top-left corner.
    failure_text = (
        "CALIBRATION FAILED\n"
        "Not enough data points"
    )
    ax_plot.text(
        0.02, 0.98, failure_text,
        transform=ax_plot.transAxes,
        fontsize=10,
        verticalalignment='top',
        bbox=dict(
            boxstyle='round,pad=0.5',
            facecolor='#FFE5E5',
            edgecolor='#CC0000',
            linewidth=2
        ),
        color='#CC0000',
        weight='bold'
    )
    
    ax_plot.set_xlabel("Observed m/z")
    ax_plot.set_ylabel("Exact m/z")
    ax_plot.set_title(title)
    
    # Disable scientific notation on both axes
    ax_plot.xaxis.set_major_formatter(ScalarFormatter(useOffset=False))
    ax_plot.yaxis.set_major_formatter(ScalarFormatter(useOffset=False))
    ax_plot.ticklabel_format(style='plain', axis='both')
    
    # Only show legend if there are data points.
    if has_calibrants:
        ax_plot.legend(loc="lower right")
        
        # Create table on the right.
        ax_table = fig.add_subplot(gs[1])
        ax_table.axis('off')
        
        # Prepare table data (sorted high to low) - only m/z and pre-cal. ppm.
        table_data = []
        for idx in sort_indices:
            table_data.append([
                f"{mzs_exact_array[idx]:.2f}",
                f"{pre_cal_errors[idx]:.1f}"
            ])
        
        # Create table with only 2 columns.
        table = ax_table.table(
            cellText=table_data,
            colLabels=["Exact m/z", "Pre-cal. ppm"],
            loc="center",
            cellLoc="center",
            colWidths=[0.5, 0.5]
        )
        
        # Style the table.
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.8)
        
        # Style header row.
        for i in range(2):
            cell = table[(0, i)]
            cell.set_facecolor('#E8E8E8')
            cell.set_text_props(weight='bold')
    
    plt.tight_layout()
    
    return fig

