from datetime import datetime
import logging
import os
import sys

from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import QApplication, QStyleFactory
from PyQt6.QtCore import qInstallMessageHandler

from sweet_suite.gui.main_window import MainWindow


def suppress_qt_warnings(_mode, _context, message):
    """Suppress Qt platform warnings for RDP sessions."""
    if "qt.qpa" in message.lower() or "monitor interface" in message.lower():
        return
    

def setup_logging() -> None:
    """Setup logging."""
    logs_folder = os.path.join(os.getcwd(), "logs")
    os.makedirs(logs_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%d-%m-%Y_%H%M")
    log_path = os.path.join(logs_folder, f"sweetsuite_{timestamp}.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path),
            logging.StreamHandler(sys.stdout)
        ]
    )


def apply_light_palette(app: QApplication) -> None:
    """Forces light-mode on the app window."""
    # Use the cross-platform Fusion style (do this before creating widgets).
    app.setStyle(QStyleFactory.create("Fusion"))
    # Build a light palette based on Qt's examples.
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(235, 235, 235))
    p.setColor(QPalette.ColorRole.WindowText, QColor(0, 0, 0))
    p.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(225, 225, 225))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 220))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(0, 0, 0))
    p.setColor(QPalette.ColorRole.Text, QColor(0, 0, 0))
    p.setColor(QPalette.ColorRole.Button, QColor(210, 210, 210))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(0, 0, 0))
    p.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
    p.setColor(QPalette.ColorRole.Link, QColor(0, 120, 215))
    p.setColor(QPalette.ColorRole.Highlight, QColor(0, 120, 215))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(p)


def main():
    # Install Qt message handler to suppress warnings.
    qInstallMessageHandler(suppress_qt_warnings)
    # Show loading screen in case of .exe file.
    if getattr(sys, "frozen", False):
        import pyi_splash
    # Setup global logging.
    setup_logging()
    logging.info("SweetSuite application started\n")
    # Create instance of QApplication.
    app = QApplication(sys.argv)
    # Apply Fusion + light palette.
    apply_light_palette(app)
    # Create and show the main window.
    main_window = MainWindow()
    main_window.show()
    # Close loading screen in case of .exe file.
    if getattr(sys, "frozen", False):
        pyi_splash.close()
    # Start application's event loop, exit when loop ends.
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

