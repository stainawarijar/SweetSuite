"""LC-FLD analysis window using the Designer form and a placeholder plot."""

import logging
import math
from pathlib import Path

import plotly.graph_objects as go
from PyQt6.QtCore import Qt, QTemporaryDir, QUrl
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QMainWindow, QMessageBox

from ..qtdesigner_files.gui_chromatogram import Ui_ChromatogramWindow

logger = logging.getLogger(__name__)
_open_viewers = set()


class ChromatogramWindow(QMainWindow):
    """Keep analysis controls native and embed Plotly in the bottom widget."""

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
            | Qt.WindowType.WindowCloseButtonHint
        )
        # Use setFixedSize below rather than the Windows dialog-border hint,
        # which interferes with per-monitor DPI changes.
        if parent is not None:
            self.setWindowIcon(parent.windowIcon())
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # File loading and analysis will be connected when processing is added.
        for button in (
            self.ui.pushButton_open_chromatogram,
            self.ui.pushButton_detect_peaks,
            self.ui.pushButton_export,
            self.ui.pushButton_clear,
        ):
            button.setEnabled(False)
            button.setToolTip("Available when chromatogram processing is implemented.")
        self.ui.path_chromatogram.addItem("Placeholder chromatogram — synthetic data")

        self.plot_view = QWebEngineView(self.ui.plotContainer)
        self.ui.plotContainer.layout().addWidget(self.plot_view)

        temporary_dir = QTemporaryDir()
        if not temporary_dir.isValid():
            raise OSError("Could not create a temporary directory for the chromatogram.")
        self._temporary_dir = temporary_dir
        self.destroyed.connect(lambda *_: temporary_dir.remove())

        times = [index / 20 for index in range(801)]
        intensities = [
            0.02 + sum(
                height * math.exp(-0.5 * ((time - center) / width) ** 2)
                for center, width, height in ((12, 0.4, 0.65), (19, 0.7, 1), (27, 0.5, 0.45))
            )
            for time in times
        ]
        figure = go.Figure(go.Scatter(
            x=times, y=intensities, mode="lines", line=dict(color="#1f77b4"),
            name="Synthetic chromatogram",
        ))
        figure.update_layout(
            template="simple_white",
            xaxis_title="Retention time (min)", yaxis_title="Relative intensity",
            xaxis_title_font_size=12, yaxis_title_font_size=12,
            margin=dict(l=60, r=20, t=45, b=45), autosize=True,
        )
        html_path = temporary_dir.filePath("chromatogram.html")
        plot_html = figure.to_html(
            full_html=False, include_plotlyjs=True, div_id="chromatogram",
            default_width="100%", default_height="100%",
            config={"responsive": True, "scrollZoom": True, "displaylogo": False,
                    "displayModeBar": True,
                    "modeBarButtonsToRemove": ["toImage"]},
        )
        # Size the document to the browser viewport, including its padding.
        # Default browser body margins otherwise push a 100%-height plot outside it.
        Path(html_path).write_text(
            '<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<style>html, body {width:100%; height:100%; margin:0; overflow:hidden;}'
            'body {padding:2px; box-sizing:border-box;}'
            'body > div {width:100%; height:100%;}</style></head><body>'
            + plot_html + '</body></html>',
            encoding="utf-8",
        )
        self.plot_view.load(QUrl.fromLocalFile(html_path))
        self.setFixedSize(launch_size)
        self.resize(launch_size)


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
