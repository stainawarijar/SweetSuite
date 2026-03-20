"""
Viewer for .xy mass spectrum files.

Opens a non-modal Qt dialog with an embedded matplotlib canvas.
The dialog (and all its data) is freed as soon as it is closed.
On zoom/pan the displayed data is resampled so large files stay fast.
"""

import logging
import os

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFileDialog, QVBoxLayout, QMessageBox

logger = logging.getLogger(__name__)

MAX_POINTS = 5000  # max data points rendered at any zoom level


class _Toolbar(NavigationToolbar2QT):
    """Minimal navigation toolbar showing only the 'Home' and 'Save' buttons."""
    toolitems = [t for t in NavigationToolbar2QT.toolitems if t[0] in ("Home", "Save")]

    def set_home_callback(self, callback) -> None:
        """Register a callable that is invoked when the Home button is pressed."""
        self._home_callback = callback

    def home(self, *args) -> None:
        """Reset the view to the full spectrum range."""
        if hasattr(self, "_home_callback"):
            self._home_callback()
        else:
            super().home(*args)


# ---------------------------------------------------------------------------
# Downsampling — min/max per bucket (never misses a peak)
# ---------------------------------------------------------------------------

def _minmax_downsample(x: np.ndarray, y: np.ndarray, n_out: int):
    n = len(x)
    if n <= n_out:
        return x, y

    n_buckets = n_out // 2
    bucket_size = n / n_buckets

    out_x = np.empty(n_buckets * 2, dtype=x.dtype)
    out_y = np.empty(n_buckets * 2, dtype=y.dtype)

    for i in range(n_buckets):
        start = int(i * bucket_size)
        end = int((i + 1) * bucket_size)
        if end > n:
            end = n
        seg_y = y[start:end]
        i_min = start + int(np.argmin(seg_y))
        i_max = start + int(np.argmax(seg_y))
        if i_min <= i_max:
            out_x[2 * i],     out_y[2 * i]     = x[i_min], y[i_min]
            out_x[2 * i + 1], out_y[2 * i + 1] = x[i_max], y[i_max]
        else:
            out_x[2 * i],     out_y[2 * i]     = x[i_max], y[i_max]
            out_x[2 * i + 1], out_y[2 * i + 1] = x[i_min], y[i_min]

    return out_x, out_y


def _get_display_data(mz, intensity, xmin, xmax):
    # mz is guaranteed sorted on load; use searchsorted to avoid O(n) masking
    start_idx = int(np.searchsorted(mz, xmin, side="left"))
    end_idx = int(np.searchsorted(mz, xmax, side="right"))
    mx = mz[start_idx:end_idx]
    my = intensity[start_idx:end_idx]
    if len(mx) > MAX_POINTS:
        mx, my = _minmax_downsample(mx, my, MAX_POINTS)
    return mx, my


# ---------------------------------------------------------------------------
# Qt dialog with embedded matplotlib canvas
# ---------------------------------------------------------------------------

class _XYSpectrumDialog(QDialog):
    """Non-modal dialog showing one .xy spectrum. Frees data on close."""

    def __init__(self, mz: np.ndarray, intensity: np.ndarray, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        # Delete C++ object (and Python referents) when the window is closed.
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(1100, 600)

        self._mz = mz
        self._intensity = intensity
        self._updating = False  # re-entrancy guard for xlim_changed
        self._full_xlim = (float(mz[0]), float(mz[-1]))  # original full range for zoom reset

        # --- matplotlib figure ---
        fig = Figure(facecolor="white", tight_layout=True)
        self._ax = fig.add_subplot(111)
        canvas = FigureCanvasQTAgg(fig)
        self._toolbar = _Toolbar(canvas, self)

        layout = QVBoxLayout(self)
        layout.addWidget(self._toolbar)
        layout.addWidget(canvas)

        # Initial draw with full range downsampled
        mx, my = _get_display_data(mz, intensity, float(mz[0]), float(mz[-1]))
        (self._line,) = self._ax.plot(mx, my, color="#003d8f", linewidth=1.5)
        self._ax.set_xlabel("m/z", fontsize=16)
        self._ax.set_ylabel("Intensity", fontsize=16)
        self._ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))

        self._pan_x_press: float | None = None   # pixel x at drag start
        self._pan_xlim_start: tuple | None = None  # xlim at drag start

        # Wire the Home button to restore the full spectrum range.
        self._toolbar.set_home_callback(lambda: self._ax.set_xlim(self._full_xlim))

        # Resample whenever the x-axis range changes (zoom / pan / home)
        self._ax.callbacks.connect("xlim_changed", self._on_xlim_changed)
        # Mouse-wheel zoom and click-drag pan
        canvas.mpl_connect("scroll_event", self._on_scroll)
        canvas.mpl_connect("button_press_event", self._on_button_press)
        canvas.mpl_connect("motion_notify_event", self._on_mouse_motion)
        canvas.mpl_connect("button_release_event", self._on_mouse_release)
        canvas.draw()

    _ZOOM_FACTOR = 1.35  # factor applied per scroll tick

    def _on_scroll(self, event) -> None:
        """Zoom in/out on the x-axis centred on the mouse cursor."""
        if event.inaxes is not self._ax or event.xdata is None:
            return
        xmin, xmax = self._ax.get_xlim()
        width = xmax - xmin
        # Guard against zero or negative width to avoid division by zero / NaNs
        if width <= 0:
            # Reset to the full spectrum range if we end up in a degenerate state
            self._ax.set_xlim(self._full_xlim)
            self._ax.figure.canvas.draw_idle()
            return
        scale = 1 / self._ZOOM_FACTOR if event.button == "down" else self._ZOOM_FACTOR
        new_width = width * scale
        # Keep the data-coordinate under the cursor stationary
        rel = (event.xdata - xmin) / width
        new_xmin = event.xdata - rel * new_width
        new_xmax = event.xdata + (1.0 - rel) * new_width
        # Clamp to data bounds
        data_xmin, data_xmax = self._full_xlim
        new_xmin = max(new_xmin, data_xmin)
        new_xmax = min(new_xmax, data_xmax)
        self._ax.set_xlim(new_xmin, new_xmax)

    def _on_button_press(self, event) -> None:
        """Start a pan drag on left-click."""
        if event.button != 1 or event.dblclick or event.inaxes is not self._ax:
            return
        self._pan_x_press = event.x
        self._pan_xlim_start = self._ax.get_xlim()

    def _on_mouse_motion(self, event) -> None:
        """Pan the spectrum while the left mouse button is held."""
        if self._pan_x_press is None or self._pan_xlim_start is None:
            return
        if event.x is None:
            return
        ax = self._ax
        xlim = self._pan_xlim_start
        ax_width_px = ax.get_window_extent().width
        if ax_width_px == 0:
            return
        data_range = xlim[1] - xlim[0]
        # Dragging right shifts the view left (negative shift in data coords)
        dx_data = -(event.x - self._pan_x_press) / ax_width_px * data_range
        new_xmin = xlim[0] + dx_data
        new_xmax = xlim[1] + dx_data
        # Clamp to data bounds while preserving the window width
        data_xmin, data_xmax = self._full_xlim
        if new_xmin < data_xmin:
            new_xmax += data_xmin - new_xmin
            new_xmin = data_xmin
        if new_xmax > data_xmax:
            new_xmin -= new_xmax - data_xmax
            new_xmax = data_xmax
        ax.set_xlim(new_xmin, new_xmax)

    def _on_mouse_release(self, event) -> None:
        """End a pan drag."""
        if event.button == 1:
            self._pan_x_press = None
            self._pan_xlim_start = None

    def _on_xlim_changed(self, ax) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            xmin, xmax = ax.get_xlim()
            mx, my = _get_display_data(self._mz, self._intensity, xmin, xmax)
            self._line.set_data(mx, my)
            ax.relim()
            ax.autoscale_view(scalex=False)  # auto-scale Y to visible data
            ax.figure.canvas.draw_idle()
        finally:
            self._updating = False


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def launch_xy_viewer(parent=None) -> None:
    """Open a file dialog then display the spectrum in a Qt dialog window."""
    filepath, _ = QFileDialog.getOpenFileName(
        parent,
        "Open mass spectrum",
        "",
        "XY files (*.xy);;All files (*.*)",
    )
    if not filepath:
        return

    logger.info("Opening XY spectrum viewer for: %s", filepath)

    try:
        data = np.loadtxt(filepath, dtype=np.float64)
    except Exception as exc:  # noqa: BLE001 - show user-facing error dialog
        logger.exception("Failed to load XY spectrum file: %s", filepath)
        QMessageBox.critical(
            parent,
            "Error opening spectrum",
            f"Could not read file:\n{filepath}\n\n{exc}",
        )
        return

    # Validate that the loaded data looks like an XY spectrum:
    # at least two columns (m/z and intensity) and more than one data point.
    if data.ndim != 2 or data.shape[1] < 2 or data.shape[0] < 2:
        logger.error(
            "XY spectrum file has invalid shape %s; expected at least two columns "
            "and more than one row.",
            getattr(data, "shape", None),
        )
        QMessageBox.warning(
            parent,
            "Invalid spectrum file",
            "The selected file does not contain a valid XY spectrum.\n\n"
            "Expected at least two columns (m/z and intensity) and more than one "
            "data point.",
        )
        return

    mz = data[:, 0]
    intensity = data[:, 1]

    # Ensure sorted by m/z for correct range slicing
    if not np.all(mz[:-1] <= mz[1:]):
        order = np.argsort(mz)
        mz, intensity = mz[order], intensity[order]

    title = f"{os.path.basename(filepath)}  ({len(mz):,} points)"
    dialog = _XYSpectrumDialog(mz, intensity, title, parent)

    # Keep a strong reference on the parent so the GC cannot collect the
    # dialog while it is still open (non-modal dialogs are otherwise only
    # referenced by a local variable that disappears when this function returns).
    if parent is not None:
        if not hasattr(parent, "_xy_viewers"):
            parent._xy_viewers = []
        parent._xy_viewers.append(dialog)
        dialog.destroyed.connect(lambda: parent._xy_viewers.remove(dialog))

    dialog.show()  # non-modal: multiple spectra can be open simultaneously
