"""LC-FLD chromatogram viewer using the Designer form and an embedded Plotly plot."""

import logging
import os
from pathlib import Path

import plotly.graph_objects as go
from PyQt6.QtCore import Qt, QTemporaryDir, QUrl
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QFileDialog, QGridLayout, QMainWindow, QMessageBox

from ...chromatography.helpers import parse_fld_txt_file
from ..qtdesigner_files.gui_chromatogram_viewer import Ui_ChromatogramWindow
from .xy_spectrum_viewer import SPECTRUM_COLORS

logger = logging.getLogger(__name__)
_open_viewers = set()


class ChromatogramWindow(QMainWindow):
    """Keep controls native and embed Plotly in the bottom widget."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.ui = Ui_ChromatogramWindow()
        self.ui.setupUi(self)
        launch_size = self.size()
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        if parent is not None:
            self.setWindowIcon(parent.windowIcon())
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self.plot_view = QWebEngineView(self.ui.plotContainer)
        self.ui.plotContainer.layout().addWidget(self.plot_view)

        temporary_dir = QTemporaryDir()
        if not temporary_dir.isValid():
            raise OSError("Could not create a temporary directory for the chromatogram.")
        self._temporary_dir = temporary_dir
        self._plot_count = 0
        self.destroyed.connect(lambda *_: temporary_dir.remove())

        self.ui.pushButton_open_chromatogram.clicked.connect(self.open_chromatograms)
        self._apply_resizable_layout()
        self.setMinimumSize(launch_size)
        self.resize(launch_size)

    def _apply_resizable_layout(self):
        """Replace the Designer's absolute geometry with a layout.

        The button and path list keep their designed height (and the button its
        width); the path list and plot container take up extra width, and the
        plot container also takes up extra height.
        """
        ui = self.ui
        ui.pushButton_open_chromatogram.setFixedSize(
            ui.pushButton_open_chromatogram.size())
        ui.path_chromatograms.setFixedHeight(ui.path_chromatograms.height())
        layout = QGridLayout(ui.centralwidget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(9)
        layout.addWidget(ui.pushButton_open_chromatogram, 0, 0,
                         Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(ui.path_chromatograms, 0, 1)
        layout.addWidget(ui.plotContainer, 1, 0, 1, 2)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(1, 1)

    def open_chromatograms(self):
        """Select FLD text files, list their paths and plot them."""
        filepaths, _ = QFileDialog.getOpenFileNames(
            self, "Open chromatograms", "", "Text files (*.txt)",
        )
        if not filepaths:
            return

        chromatograms, errors = [], []
        for filepath in filepaths:
            try:
                data = parse_fld_txt_file(filepath)
                if data.ndim != 2 or len(data) < 2:
                    raise ValueError("No chromatogram data found.")
            except Exception as exc:
                logger.exception("Failed to load chromatogram: %s", filepath)
                errors.append(f"{filepath}: {exc}")
                continue
            chromatograms.append((filepath, data))
        if errors:
            QMessageBox.warning(self, "Could not open chromatograms", "\n\n".join(errors))
        if not chromatograms:
            return

        self.ui.path_chromatograms.clear()
        self.ui.path_chromatograms.addItems([path for path, _ in chromatograms])
        self.plot_chromatograms(chromatograms)

    def plot_chromatograms(self, chromatograms):
        """Overlay chromatograms, each in its own color."""
        basenames = [os.path.basename(path) for path, _ in chromatograms]
        figure = go.Figure()
        for index, ((path, data), basename) in enumerate(zip(chromatograms, basenames)):
            figure.add_trace(go.Scatter(
                x=data[:, 0], y=data[:, 1], mode="lines",
                name=path if basenames.count(basename) > 1 else basename,
                line=dict(color=SPECTRUM_COLORS[index % len(SPECTRUM_COLORS)]),
            ))
        figure.update_layout(
            template="simple_white",
            xaxis_title="Retention time (min)", yaxis_title="Intensity",
            xaxis_title_font_size=12, yaxis_title_font_size=12,
            legend=dict(orientation="h", x=0.5, xanchor="center", y=-0.2, yanchor="top"),
            margin=dict(l=60, r=20, t=20, b=45), autosize=True,
        )
        plot_html = figure.to_html(
            full_html=False, include_plotlyjs=True, div_id="chromatogram",
            default_width="100%", default_height="100%",
            config={"responsive": True, "scrollZoom": True, "displaylogo": False,
                    "displayModeBar": True,
                    "modeBarButtonsToRemove": ["toImage"]},
        )
        # Size the document to the browser viewport, including its padding.
        # Default browser body margins otherwise push a 100%-height plot outside it.
        self._plot_count += 1
        html_path = self._temporary_dir.filePath(f"chromatogram_{self._plot_count}.html")
        Path(html_path).write_text(
            '<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<style>html, body {width:100%; height:100%; margin:0; overflow:hidden;}'
            'body {padding:2px; box-sizing:border-box;}'
            'body > div {width:100%; height:100%;}</style></head><body>'
            + plot_html + '</body></html>',
            encoding="utf-8",
        )
        self.plot_view.load(QUrl.fromLocalFile(html_path))


def launch_chromatogram_viewer(parent=None):
    """Open a non-modal viewer and keep it alive until it is closed."""
    try:
        window = ChromatogramWindow(parent)
    except Exception as exc:
        logger.exception("Failed to create LC-FLD chromatogram viewer")
        QMessageBox.critical(parent, "Error opening chromatogram viewer", str(exc))
        return
    _open_viewers.add(window)
    window.destroyed.connect(lambda *_: _open_viewers.discard(window))
    window.show()
    return window
