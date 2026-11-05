from PySide6.QtGui import QPixmap, Qt
from PySide6.QtWidgets import QLabel

from gui.gui_utils.helpers import colorize_pixmap


class HelpIcon(QLabel):
    def __init__(self, parent, tooltip):
        super().__init__(parent=parent)
        self.parent = parent
        pixmap = colorize_pixmap(QPixmap(':/resources/icon-info.png'), opacity=0.5)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(12, 12, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(pixmap)
        self.setToolTip(tooltip)
