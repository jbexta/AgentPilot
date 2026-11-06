from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QPushButton

from gui.gui_utils.helpers import Attention, colorize_pixmap
from utils.helpers import path_to_pixmap


class IconButton(QPushButton):
    def __init__(
            self,
            parent,
            icon_path=None,
            hover_icon_path=None,
            target=None,
            size=25,
            tooltip=None,
            icon_size_percent=0.75,
            colorize=True,
            opacity=1.0,
            text=None,
            checkable=False,
            **kwargs,
    ):
        super().__init__(parent=parent)
        self.parent = parent
        self.colorize = colorize
        self.opacity = opacity

        self.icon = None
        self.notification_dot = Attention.NONE
        # if isinstance(icon_path, str):
        self.pixmap = path_to_pixmap(icon_path, diameter=size, opacity=opacity)  if icon_path else QPixmap(0, 0)
        # copy of pixmap to restore when leaving hover state
        self.original_pixmap = self.pixmap.copy()
        self.hover_pixmap = QPixmap(hover_icon_path) if hover_icon_path else None
        self.target = target
        self.clicked.connect(self.on_click)

        character_width = 8
        width = size + (len(text) * character_width if text else 0)
        self.icon_size = int(size * icon_size_percent)
        # self.setFixedSize(width, size)
        self.resize(width, size)
        self.setIconSize(QSize(self.icon_size, self.icon_size))
        self.setIconPixmap(self.pixmap)

        self.setAutoExclusive(False)  # To disable visual selection

        if tooltip:
            self.setToolTip(tooltip)
        if text:
            self.setText(text)
        if checkable:
            self.setCheckable(True)

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        self.opacity = 1 if enabled else 0.30
        self.setIconPixmap(self.pixmap)

    def on_click(self):
        if self.target:
            self.target()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.notification_dot:
            painter = QPainter(self)
            color = QColor(self.notification_dot.color)
            painter.setPen(color)
            painter.setBrush(color)
            radius = 4
            painter.drawEllipse(self.rect().right() - radius * 2 - 4, 4, radius * 2, radius * 2)
            painter.end()

    def setIconPixmap(self, pixmap=None, color=None):
        if not pixmap:
            pixmap = self.pixmap
        self.pixmap = pixmap

        if self.colorize:
            pixmap = colorize_pixmap(pixmap, opacity=self.opacity, color=color)

        self.icon = QIcon(pixmap)
        self.setIcon(self.icon)

    def enterEvent(self, event):
        if self.hover_pixmap:
            self.setIconPixmap(self.hover_pixmap)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.hover_pixmap:
            if self.original_pixmap.isNull():
                self.setIcon(QIcon())  # Clear the icon completely
            else:
                self.setIconPixmap(self.original_pixmap)
        super().leaveEvent(event)
