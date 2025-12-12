from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDoubleSpinBox, QMessageBox, QSpinBox


class UIHelpers:
    """Utility class for common UI operations."""
    
    @staticmethod
    def show_message_box(
        parent,
        title: str,
        text: str,
        informative_text: str | None = "",
        icon: str = "NoIcon"
    ) -> None:
        """Show a message box with an icon and rich text.
        
        Args:
            parent: Parent widget.
            title: Title of the message box. 
            text: Main message to show in the box.
            informative_text: Extra informative text to show below
                the main text.
            icon: Icon to show in the box.  Possibilities are: `Warning`,
                `Information`, `Critical`, `Question`.  Shows no icon 
                by default.
        """
        msg_box = QMessageBox(parent)
        msg_box.setWindowTitle(title)
        msg_box.setIcon(QMessageBox.Icon[icon])
        msg_box.setText(f"<b>{text}</b>")
        if informative_text is not None:
            msg_box.setInformativeText(informative_text)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.setTextFormat(Qt.TextFormat.RichText)
        msg_box.exec()
    
    @staticmethod
    def disable_spinbox_scroll(parent_widget) -> None:
        """Disable mouse scrolling for all spinbox widgets.
        
        Args:
            parent_widget: Parent widget to search for spinboxes.
        """
        for spinbox in parent_widget.findChildren(QSpinBox):
            spinbox.wheelEvent = lambda event: event.ignore()
        for spinbox in parent_widget.findChildren(QDoubleSpinBox):
            spinbox.wheelEvent = lambda event: event.ignore()