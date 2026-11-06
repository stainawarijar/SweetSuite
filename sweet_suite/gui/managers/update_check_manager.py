"""Notification-only release checks; remote content is never executed."""

import json
from pathlib import Path
import re
import sys

from PyQt6.QtCore import QObject, QSaveFile, QIODevice, QTimer, Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import QCheckBox, QMessageBox

from sweet_suite import __version__


# Keep network and browser destinations fixed; never trust URLs in release metadata.
API_URL = "https://api.github.com/repos/stainawarijar/SweetSuite/releases/latest"
RELEASE_URL = "https://github.com/stainawarijar/SweetSuite/releases/tag/"
MAX_RESPONSE_BYTES = 1024 * 1024
TIMEOUT_MS = 5000


def parse_version(value: str) -> tuple[int, int, int]:
    """Return a numeric version tuple, accepting an optional 'v' prefix.
    
    Args: 
        value: The version number 'x.y.z' as a string, optionally containing
            a 'v' prefix.
    
    Returns:
        A tuple containing major (x), minor (y) and patch (z) version numbers
        as integers (x, y, z).
    """
    # Metadata is untrusted: accept only numeric versions, excluding URL/path syntax
    # and markup before a tag is used in a browser URL.
    if not isinstance(value, str):
        return
    if re.fullmatch(r"v?[0-9]+\.[0-9]+\.[0-9]+", value) is None:
        return
    return tuple(int(part) for part in value.removeprefix("v").split("."))


def normalized_version(value):
    """Returns the version as a string without the optional 'v' prefix."""
    version = parse_version(value)
    if version is None:
        return
    return ".".join(map(str, version))


def ignore_file_path():
    """Use the installed copy's directory, never the bundle extraction path."""
    directory = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parents[3]
    )
    return directory / ".ignoreupdate"


class UpdateMessageBox(QMessageBox):
    """Dismiss Escape without activating the Ignore button.
    """
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)


class UpdateCheckManager(QObject):
    """Own one bounded asynchronous check and its optional update dialog.
    """
    def __init__(self, parent, current_version=__version__, ignore_path=None):
        super().__init__(parent)
        self.current_version = current_version
        self.ignore_path = Path(ignore_path) if ignore_path is not None else ignore_file_path()
        self.network = QNetworkAccessManager(self)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._discard_reply)
        self.reply = None
        self.dialog = None
        self._body = bytearray()
        self._started = False
        self._stopped = False

    def start(self):
        """Start once, returning immediately to the GUI event loop."""
        if self._started or self._stopped or parse_version(self.current_version) is None:
            return
        self._started = True
        request = QNetworkRequest(QUrl(API_URL))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"User-Agent", b"SweetSuite-UpdateCheck")
        # Do not follow redirects to another host or to unencrypted HTTP.
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.ManualRedirectPolicy
        )
        # Bound both idle time and total request time (the separate timer below).
        request.setTransferTimeout(TIMEOUT_MS)
        self.reply = self.network.get(request)
        self.reply.setReadBufferSize(MAX_RESPONSE_BYTES + 1)
        self.reply.readyRead.connect(self._read_available)
        self.reply.finished.connect(self._finished)
        # Keep Qt certificate verification enabled; never ignore TLS errors.
        self.reply.sslErrors.connect(self._discard_reply)
        self.timer.start(TIMEOUT_MS)

    def _read_available(self):
        if self.reply is None:
            return
        # Read at most one byte beyond the limit so oversized bodies are rejected
        # without accumulating the entire response in application memory.
        remaining = MAX_RESPONSE_BYTES - len(self._body)
        data = self.reply.read(remaining + 1)
        if data is None:  # PyQt may return None when the reply is at EOF.
            return
        self._body.extend(bytes(data))
        if len(self._body) > MAX_RESPONSE_BYTES:
            self._discard_reply()

    def _discard_reply(self, *_args):
        self.timer.stop()
        reply, self.reply = self.reply, None
        self._body.clear()
        if reply is not None:
            reply.abort()
            reply.deleteLater()

    def _finished(self):
        if self.reply is None:
            return
        self._read_available()
        if self.reply is None:
            return
        self.timer.stop()
        reply, self.reply = self.reply, None
        # Only a successful response is eligible for parsing; redirects and errors
        # must not produce an update prompt.
        valid = (
            reply.error() == QNetworkReply.NetworkError.NoError and
            reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) == 200
        )
        body = bytes(self._body)
        self._body.clear()
        reply.deleteLater()
        if not valid or self._stopped:
            return
        try:
            # Decode data only: never evaluate or execute remote release content.
            metadata = json.loads(body)
        except (ValueError, UnicodeError, RecursionError):
            return
        if not isinstance(metadata, dict):
            return
        if metadata.get("draft") is not False or metadata.get("prerelease") is not False:
            return
        tag = metadata.get("tag_name")
        latest = parse_version(tag)
        if latest is None or latest <= parse_version(self.current_version):
            return
        version = normalized_version(tag)
        if self._ignored_version() != version:
            # Construct the link from our fixed repository and validated tag;
            # ignore the response's html_url and asset download URLs.
            self._show_update(version, RELEASE_URL + tag)

    def _ignored_version(self):
        try:
            with self.ignore_path.open("r", encoding="utf-8") as file:
                # Local preference files can also be malformed or unexpectedly large.
                value = file.read(65)
            return normalized_version(value.strip()) if len(value) <= 64 else None
        except (OSError, UnicodeError):
            return None

    def _save_ignored_version(self, version):
        # Atomically replace the preference file so failed writes do not leave
        # partial contents. The filename is local, never supplied by the server.
        file = QSaveFile(str(self.ignore_path))
        data = version.encode("utf-8")
        if not file.open(QIODevice.OpenModeFlag.WriteOnly):
            return False
        if file.write(data) != len(data):
            file.cancelWriting()
            return False
        return file.commit()

    def _show_update(self, version, url):
        box = UpdateMessageBox(self.parent())
        box.setWindowTitle("SweetSuite update available")
        box.setIcon(QMessageBox.Icon.Information)
        # Display text literally rather than interpreting it as HTML.
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText("A newer version of SweetSuite is available.")
        box.setInformativeText(
            f"Installed version: {self.current_version}\nAvailable version: {version}"
        )
        checkbox = QCheckBox("Don't remind me again for this version", box)
        box.setCheckBox(checkbox)
        ignore = box.addButton("Ignore", QMessageBox.ButtonRole.RejectRole)
        get_latest = box.addButton("Get latest version", QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(ignore)
        box.setEscapeButton(ignore)
        # Window dismissal must not persist the checkbox preference.
        def clicked(button):
            if button is get_latest:
                # Browser navigation requires this explicit click; no automatic
                # download, installation, or execution is performed.
                QDesktopServices.openUrl(QUrl(url))
            elif button is ignore and checkbox.isChecked():
                if not self._save_ignored_version(version):
                    self._show_save_failure()
        box.buttonClicked.connect(clicked)
        box.finished.connect(lambda _result: self._release_dialog(box))
        self.dialog = box
        box.open()

    def _release_dialog(self, box):
        if self.dialog is box:
            self.dialog = None
        box.deleteLater()

    def _show_save_failure(self):
        box = QMessageBox(self.parent())
        box.setWindowTitle("Update preference not saved")
        box.setText("The update preference could not be saved. You may be reminded again next time.")
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.open()

    def stop(self):
        """Cancel pending work before the application exits."""
        self._stopped = True
        self._discard_reply()
        if self.dialog is not None:
            self.dialog.reject()
