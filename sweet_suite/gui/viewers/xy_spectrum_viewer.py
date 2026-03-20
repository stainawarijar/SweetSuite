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
    """Standard navigation toolbar with the 'Figure options' button removed."""
    toolitems = [t for t in NavigationToolbar2QT.toolitems if t[0] not in ("Customize", "Subplots")]


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
        toolbar = _Toolbar(canvas, self)

        layout = QVBoxLayout(self)
        layout.addWidget(toolbar)
        layout.addWidget(canvas)

        # Initial draw with full range downsampled
        mx, my = _get_display_data(mz, intensity, float(mz[0]), float(mz[-1]))
        (self._line,) = self._ax.plot(mx, my, color="#003d8f", linewidth=1.5)
        self._ax.set_xlabel("m/z", fontsize=16)
        self._ax.set_ylabel("Intensity", fontsize=16)
        self._ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))

        # Resample whenever the x-axis range changes (zoom / pan / home)
        self._ax.callbacks.connect("xlim_changed", self._on_xlim_changed)
        # Mouse-wheel zoom and double-click reset
        canvas.mpl_connect("scroll_event", self._on_scroll)
        canvas.mpl_connect("button_press_event", self._on_button_press)
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
        scale = 1 / self._ZOOM_FACTOR if event.button == "up" else self._ZOOM_FACTOR
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
        """Reset zoom to the full spectrum on double-click."""
        if event.dblclick and event.inaxes is self._ax:
            self._ax.set_xlim(self._full_xlim)

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
    dialog.show()  # non-modal: multiple spectra can be open simultaneously
