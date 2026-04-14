from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from gui.style import ACCENT_COLOR_1


class ComputerUseOverlay(QWidget):
    """Transparent, click-through glow on left/right screen edges."""

    STRIP_WIDTH = 40
    EDGE_ALPHA = 180

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

    def show_overlay(self):
        """Position to cover the full screen and show."""
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.show()
        self.raise_()

    def hide_overlay(self):
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        strip = self.STRIP_WIDTH

        color = QColor(ACCENT_COLOR_1)
        edge_color = QColor(color.red(), color.green(), color.blue(),
                            self.EDGE_ALPHA)
        transparent = QColor(color.red(), color.green(), color.blue(), 0)

        # Left edge glow
        left_grad = QLinearGradient(0, 0, strip, 0)
        left_grad.setColorAt(0.0, edge_color)
        left_grad.setColorAt(1.0, transparent)
        painter.fillRect(0, 0, strip, h, left_grad)

        # Right edge glow
        right_grad = QLinearGradient(w - strip, 0, w, 0)
        right_grad.setColorAt(0.0, transparent)
        right_grad.setColorAt(1.0, edge_color)
        painter.fillRect(w - strip, 0, strip, h, right_grad)

        painter.end()