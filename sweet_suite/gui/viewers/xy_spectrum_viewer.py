"""View .xy mass spectra with Plotly Express in an embedded Qt dialog."""

import logging
import os
import json

import numpy as np
import plotly.express as px
from PyQt6.QtCore import Qt, QTemporaryDir, QUrl, pyqtSlot
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QDialog, QFileDialog, QMessageBox, QVBoxLayout

logger = logging.getLogger(__name__)


_open_viewers = set()
MAX_POINTS = 10000  # rendering budget per spectrum
MAX_SPECTRA = 10
SPECTRUM_COLORS = (
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
)


def display_data(mz, intensity, xmin, xmax, max_points=MAX_POINTS):
    """Keep each bucket's extremes, with neighbouring points at view edges."""
    start = max(0, int(np.searchsorted(mz, xmin, side="left")) - 1)
    end = min(len(mz), int(np.searchsorted(mz, xmax, side="right")) + 1)
    x, y = mz[start:end], intensity[start:end]
    if len(x) <= max_points:
        return x, y
    edges = np.linspace(0, len(x), (max_points - 2) // 2 + 1, dtype=int)
    indices = [0, len(x) - 1]
    for left, right in zip(edges[:-1], edges[1:]):
        bucket = y[left:right]
        indices.extend((left + int(np.argmin(bucket)), left + int(np.argmax(bucket))))
    indices = np.unique(indices)
    return x[indices], y[indices]


_ZOOM_SCRIPT = """
const plot = document.getElementById('{plot_id}');
const channelScript = document.createElement('script');
channelScript.src = 'qrc:///qtwebchannel/qwebchannel.js';
channelScript.onload = function () {
    new QWebChannel(qt.webChannelTransport, function (channel) {
        let timer;
        plot.on('plotly_relayout', function (event) {
            if (!Object.keys(event).some(key => key.startsWith('xaxis.'))) return;
            clearTimeout(timer);
            timer = setTimeout(function () {
                const range = event['xaxis.autorange']
                    ? [FULL_MIN, FULL_MAX]
                    : plot._fullLayout.xaxis.range;
                channel.objects.spectrumViewer.updateRange(range[0], range[1]);
            }, 100);
        });
    });
};
document.head.appendChild(channelScript);
"""


class _XYSpectrumDialog(QDialog):
    """Display a self-contained Plotly figure and release it on close."""

    def __init__(self, spectra, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mass spectrum viewer")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(1100, 600)
        self._spectra = spectra
        self._points_per_spectrum = MAX_POINTS
        full_min = min(mz[0] for _, mz, _ in spectra)
        full_max = max(mz[-1] for _, mz, _ in spectra)
        fig = px.line()
        fig.data = ()
        for index, (name, mz, intensity) in enumerate(spectra):
            x, y = display_data(mz, intensity, full_min, full_max, self._points_per_spectrum)
            trace = px.line(x=x, y=y, render_mode="svg").data[0]
            trace.update(
                name=name, showlegend=True,
                line=dict(color=SPECTRUM_COLORS[index]),
            )
            fig.add_trace(trace)
        fig.update_layout(
            template="simple_white",
            xaxis_title="m/z", yaxis_title="Intensity",
            legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.2, yanchor="top"),
        )

        temporary_dir = QTemporaryDir()
        if not temporary_dir.isValid():
            raise OSError("Could not create a temporary directory for the spectrum.")
        self._temporary_dir = temporary_dir
        self.destroyed.connect(lambda *_: temporary_dir.remove())
        html_path = temporary_dir.filePath("spectrum.html")
        zoom_script = _ZOOM_SCRIPT.replace("FULL_MIN", json.dumps(float(full_min)))
        zoom_script = zoom_script.replace("FULL_MAX", json.dumps(float(full_max)))
        fig.write_html(
            html_path, include_plotlyjs=True, div_id="spectrum",
            config={"responsive": True, "scrollZoom": True, "showSendToCloud": False},
            post_script=zoom_script,
        )

        self._view = QWebEngineView(self)
        # A private profile keeps image exports local to this viewer.
        self._profile = QWebEngineProfile(self)
        self._view.setPage(QWebEnginePage(self._profile, self._view))
        self._channel = QWebChannel(self._view.page())
        self._channel.registerObject("spectrumViewer", self)
        self._view.page().setWebChannel(self._channel)
        self._profile.downloadRequested.connect(self.save_image)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)
        self._view.load(QUrl.fromLocalFile(html_path))

    @pyqtSlot(float, float)
    def updateRange(self, xmin, xmax):
        if not np.isfinite(xmin) or not np.isfinite(xmax):
            return
        displayed = [
            display_data(mz, intensity, min(xmin, xmax), max(xmin, xmax), self._points_per_spectrum)
            for _, mz, intensity in self._spectra
        ]
        payload = json.dumps({
            "x": [x.tolist() for x, _ in displayed],
            "y": [y.tolist() for _, y in displayed],
        }, allow_nan=False)
        indices = json.dumps(list(range(len(self._spectra))))
        self._view.page().runJavaScript(
            f"Plotly.restyle(document.getElementById('spectrum'), {payload}, {indices});"
        )

    def save_image(self, download):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save spectrum image", download.downloadFileName(),
            "PNG images (*.png);;All files (*.*)",
        )
        if filepath:
            download.setDownloadDirectory(os.path.dirname(os.path.abspath(filepath)))
            download.setDownloadFileName(os.path.basename(filepath))
            download.accept()
        else:
            download.cancel()


def load_spectrum(filepath):
    """Load and validate a spectrum, connecting points in ascending m/z order."""
    data = np.loadtxt(filepath, dtype=np.float64)
    if data.ndim != 2 or data.shape[1] < 2 or data.shape[0] < 2:
        raise ValueError("Expected at least two columns (m/z and intensity) and more than one data point.")
    if not np.isfinite(data[:, :2]).all():
        raise ValueError("Spectrum values must be finite numbers.")
    mz, intensity = data[:, 0], data[:, 1]
    if not np.all(mz[:-1] <= mz[1:]):
        order = np.argsort(mz)
        mz, intensity = mz[order], intensity[order]
    return mz, intensity


def launch_xy_viewer(parent=None) -> None:
    """Select up to ten spectra and overlay them in an embedded Qt dialog."""
    while True:
        filepaths, _ = QFileDialog.getOpenFileNames(
            parent,
            f"Open mass spectra (maximum {MAX_SPECTRA} files)",
            "",
            "XY files (*.xy);;All files (*.*)",
        )
        if not filepaths:
            return
        if len(filepaths) <= MAX_SPECTRA:
            break
        QMessageBox.warning(
            parent, "Too many spectra",
            f"Please select at most {MAX_SPECTRA} files to keep the viewer responsive.",
        )

    spectra, errors = [], []
    basenames = [os.path.basename(filepath) for filepath in filepaths]
    for filepath, basename in zip(filepaths, basenames):
        logger.info("Opening XY spectrum viewer for: %s", filepath)
        try:
            mz, intensity = load_spectrum(filepath)
        except Exception as exc:
            logger.exception("Failed to load XY spectrum file: %s", filepath)
            errors.append(f"{filepath}: {exc}")
            continue
        name = filepath if basenames.count(basename) > 1 else basename
        spectra.append((name, mz, intensity))
    if errors:
        QMessageBox.warning(parent, "Could not open spectra", "\n\n".join(errors))
    if not spectra:
        return

    try:
        dialog = _XYSpectrumDialog(spectra, parent)
    except Exception as exc:
        logger.exception("Failed to create XY spectrum viewer")
        QMessageBox.critical(parent, "Error opening spectrum", str(exc))
        return
    _open_viewers.add(dialog)
    dialog.destroyed.connect(lambda *_: _open_viewers.discard(dialog))
    dialog.show()
