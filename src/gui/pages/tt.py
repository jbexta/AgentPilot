
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QBrush, QColor
from PySide6.QtWidgets import QWidget

from gui.gui_utils.layouts import CVBoxLayout
from gui.widgets.config_widget import ConfigWidget


class RedCircleWidget(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor('red')))
        painter.setPen(Qt.NoPen)
        size = min(self.width(), self.height())
        radius = size // 4
        cx, cy = self.width() // 2, self.height() // 2
        painter.drawEllipse(cx - radius, cy - radius,
                            radius * 2, radius * 2)
        painter.end()


class Page_Tt_Settings(ConfigWidget):
    display_name = """tt"""
    page_type = 'main'
    icon_path = ':/resources/icon-tasks.png'

    def __init__(self, parent):
        super().__init__(parent=parent)
        self.layout = CVBoxLayout(self)
        self.circle = RedCircleWidget(self)
        self.layout.addWidget(self.circle)
