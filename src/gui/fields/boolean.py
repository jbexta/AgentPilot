from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import QCheckBox


class Boolean(QCheckBox):
    option_schema = [
        {
            'text': 'Style',
            'key': 'f_style',
            'type': ('switch', 'checkbox'),
            'default': 'switch',
        },
    ]

    def __init__(self, parent, **kwargs):
        super().__init__(parent)
        self.is_switch = kwargs.get('style', 'switch') == 'switch'
        if self.is_switch:
            self.setCursor(Qt.PointingHandCursor)
        self.stateChanged.connect(parent.update_config)

    def sizeHint(self):
        return QSize(34, 20) if self.is_switch else super().sizeHint()

    def hitButton(self, pos):
        if self.is_switch:
            return self.rect().contains(pos)
        return super().hitButton(pos)

    def paintEvent(self, event):
        if not self.is_switch:
            return super().paintEvent(event)

        track = QRectF(0, 0, 34, 20)
        track.moveCenter(QRectF(self.rect()).center())
        knob = QRectF(0, 0, 16, 16)
        knob.moveCenter(track.center())
        knob.moveLeft(track.right() - 18 if self.isChecked() else track.left() + 2)

        if self.isChecked():
            track_color = self.palette().color(QPalette.Highlight)
        else:
            track_color = QColor(self.palette().color(QPalette.Text))
            track_color.setAlpha(60)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        if not self.isEnabled():
            painter.setOpacity(0.4)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, 10, 10)
        painter.setBrush(Qt.white)
        painter.drawEllipse(knob)

    def get_value(self):
        return self.isChecked()

    def set_value(self, value):
        if not isinstance(value, bool):
            if isinstance(value, str):
                value = value.lower()
            value = value in [1, '1', 'true', 'yes', 'on']
        self.setChecked(value)

    def clear_value(self):
        self.setChecked(False)
