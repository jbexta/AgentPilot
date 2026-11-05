import math
from itertools import product

from PySide6.QtCore import QPointF, QTimer
from PySide6.QtGui import QPainter, QBrush, QColor, QLinearGradient, QPen
from PySide6.QtWidgets import QWidget

from gui.gui_utils.layouts import CVBoxLayout
from gui.widgets.config_widget import ConfigWidget
from utils.helpers import set_module_type

VERTICES = list(product((-1, 1), repeat=4))
EDGES = [
    (i, j)
    for i in range(len(VERTICES))
    for j in range(i + 1, len(VERTICES))
    if sum(a != b for a, b in zip(VERTICES[i], VERTICES[j])) == 1
]
NEAR_COLOR = QColor('#E8C8FF')
FAR_COLOR = QColor('#7A2EC2')


def depth_color(t):
    near, far = NEAR_COLOR.getRgbF(), FAR_COLOR.getRgbF()
    return QColor.fromRgbF(*(f + (n - f) * t for n, f in zip(near, far)))


def project(vertex, angle, yaw, pitch):
    x, y, z, w = vertex
    c, s = math.cos(angle), math.sin(angle)
    x, w = x * c - w * s, x * s + w * c
    c, s = math.cos(angle * 0.7), math.sin(angle * 0.7)
    y, w = y * c - w * s, y * s + w * c
    f = 1 / (3 - w)
    x, y, z = x * f, y * f, z * f
    c, s = math.cos(yaw), math.sin(yaw)
    x, z = x * c - z * s, x * s + z * c
    c, s = math.cos(pitch), math.sin(pitch)
    y, z = y * c - z * s, y * s + z * c
    g = 2 / (3 - z)
    return x * g, y * g, z


@set_module_type('Pages')
class Page_Tttt_Settings(ConfigWidget):
    display_name = """tttt"""
    page_type = 'main'
    icon_path = ':/resources/icon-tasks.png'

    def __init__(self, parent):
        super().__init__(parent=parent)
        self.layout = CVBoxLayout(self)
        self.layout.addStretch(1)
        self.setMouseTracking(True)
        self.mouse_pos = None
        self.angle = 0.0
        self.yaw = 0.5
        self.pitch = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.step)
        self.timer.start(16)

    def radius(self):
        return min(self.width(), self.height()) // 8

    def center(self):
        return QPointF(self.width() / 2, self.height() / 2)

    def mouseMoveEvent(self, event):
        self.mouse_pos = event.position()
        super().mouseMoveEvent(event)

    def step(self):
        self.angle += 0.02
        self.update()
        if self.mouse_pos is None:
            return
        offset = self.mouse_pos - self.center()
        target_yaw = offset.x() / max(self.width() / 2, 1) * math.pi
        target_pitch = -offset.y() / max(self.height() / 2, 1) * math.pi
        self.yaw += (target_yaw - self.yaw) * 0.08
        self.pitch += (target_pitch - self.pitch) * 0.08

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        radius = self.radius()
        pos = self.center()
        scale = radius * 1.6
        projected = [
            project(v, self.angle, self.yaw, self.pitch) for v in VERTICES
        ]
        points = [
            pos + QPointF(px * scale, py * scale) for px, py, _ in projected
        ]
        depths = [z for _, _, z in projected]
        far = min(depths)
        span = (max(depths) - far) or 1
        colors = [depth_color((z - far) / span) for z in depths]
        for i, j in EDGES:
            gradient = QLinearGradient(points[i], points[j])
            gradient.setColorAt(0, colors[i])
            gradient.setColorAt(1, colors[j])
            painter.setPen(QPen(QBrush(gradient), 2))
            painter.drawLine(points[i], points[j])
        painter.end()
