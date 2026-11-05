
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QBrush, QColor
from PySide6.QtWidgets import QWidget

from gui.gui_utils.layouts import CVBoxLayout, CHBoxLayout
from gui.widgets.config_pages import ConfigPages


class RedCircleWidget(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor('red')))
        painter.setPen(Qt.NoPen)
        size = min(self.width(), self.height())
        radius = size // 4
        cx = self.width() // 2
        cy = self.height() // 2
        painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
        painter.end()


class Page_Ttt_Settings(ConfigPages):
    display_name = """ttt"""
    page_type = 'main'
    icon_path = ':/resources/icon-tasks.png'

    def __init__(self, parent):
        super().__init__(parent=parent)
        self.pages = {}

        circle = RedCircleWidget(self)
        self.layout = CVBoxLayout(self)
        self.layout.addWidget(circle)
