"""Standalone image preview widget.

Displays an image scaled to 250px default, with click-to-toggle
zoom to full size.
"""

from PySide6.QtCore import QPoint, QSize
from PySide6.QtGui import Qt, QImage, QPixmap
from PySide6.QtWidgets import QWidget, QLabel, QSizePolicy

from gui.util import CVBoxLayout

_POPUP_MAX = 500


class ImagePreview(QWidget):
    """Reusable image preview with click-to-zoom."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.image = None
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)

        self.layout = CVBoxLayout(self)
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setMinimumSize(5, 5)
        self.label.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        self.layout.addWidget(self.label)

        # self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # self.setMinimumSize(5, 5)

    def set_filepath(self, filepath):
        """Load and display an image from *filepath*.

        Parameters
        ----------
        filepath : str
            Absolute path to an image file.
        """
        self.image = QImage(filepath)
        if self.image.isNull():
            self.label.setText(f"Error loading image: {filepath}")
            return
        self._update_display()

    def _update_display(self):
        if self.image is None or self.image.isNull():
            return
        pixmap = QPixmap.fromImage(self.image)
        scaled = pixmap.scaled(
            self.label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_display()

    # -- hover popup ----------------------------------------------------

    def enterEvent(self, event):
        super().enterEvent(event)
        if self.image is None or self.image.isNull():
            return
        self._popup = _ImagePopup(self.image)
        # Position above the widget, centred horizontally.
        global_pos = self.mapToGlobal(QPoint(0, 0))
        px = global_pos.x() + (self.width() - self._popup.width()) // 2
        py = global_pos.y() - self._popup.height() - 4
        self._popup.move(px, py)
        self._popup.show()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if hasattr(self, '_popup') and self._popup is not None:
            self._popup.close()
            self._popup = None


class _ImagePopup(QWidget):
    """Frameless tooltip-like popup showing an enlarged image."""

    def __init__(self, image):
        super().__init__(None)
        self.setWindowFlags(
            Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        pixmap = QPixmap.fromImage(image)
        scaled = pixmap.scaled(
            QSize(_POPUP_MAX, _POPUP_MAX),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        label = QLabel(self)
        label.setPixmap(scaled)
        label.setFixedSize(scaled.size())
        self.setFixedSize(scaled.size())
