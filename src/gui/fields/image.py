"""
Image field widget for configurable image selection and display.

This module provides an Image field widget that extends QLabel to create
an interactive image picker and display component. It supports circular and
rectangular image display, drag-and-drop functionality, and popup-based
image selection via ImageSettings. The widget automatically handles image
loading, scaling, and path management, integrating with the configuration
system for persistent image storage.
"""

from PySide6.QtCore import QEvent, QTimer, Signal
from PySide6.QtGui import QColor, Qt, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from utils.filesystem import unsimplify_path
from utils.helpers import path_to_pixmap, set_module_type


class _ImageSettingsPopup(QWidget):
    """Popup wrapper around ImageSettings for the Image field.

    Uses Tool window flags instead of Popup so that child dialogs
    (e.g. QFileDialog from the file picker) don't cause auto-dismiss.
    Dismisses itself on focus loss unless a modal dialog is active.
    """

    def __init__(self, image_field):
        super().__init__()
        self.image_field = image_field
        self.config = {}
        self.propagate_config = True

        self.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
        )
        self.setFixedWidth(420)

        from plugins.workflows.widgets.image_settings import ImageSettings
        from gui.util import CVBoxLayout
        layout = CVBoxLayout(self)
        self.image_settings = ImageSettings(parent=self)
        layout.addWidget(self.image_settings)
        self.image_settings.build_schema()

    def update_config(self):
        config = self.image_settings.get_config()
        path = config.get('browse.path', '')
        if path and path != self.image_field.avatar_path:
            self.image_field.set_value(path)

    def showEvent(self, event):
        super().showEvent(event)
        pos = self.image_field.mapToGlobal(
            self.image_field.rect().bottomLeft()
        )
        self.move(pos)

    def event(self, event):
        if event.type() == QEvent.WindowDeactivate:
            if not QApplication.activeModalWidget():
                self.hide()
        return super().event(event)


@set_module_type('Fields')
class Image(QLabel):
    clicked = Signal()
    avatarChanged = Signal()

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self.avatar_path = None
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.diameter = kwargs.get('diameter', 50)
        self.circular = kwargs.get('circular', True)
        border = kwargs.get('border', True)
        from gui.style import TEXT_COLOR
        border_ss = f"border: 1px dashed {TEXT_COLOR};" if border else ""
        radius = int(self.diameter / 2) if self.circular else 0
        circular_ss = f"border-radius: {str(radius)}px;"
        self.setStyleSheet(
            f"{border_ss} {circular_ss} background-color: transparent;")
        self.setFixedSize(self.diameter, self.diameter)
        self.clicked.connect(self.change_avatar)
        self.avatarChanged.connect(parent.update_config)

    def get_value(self):
        return self.avatar_path

    def set_value(self, path):
        if not path:
            path = ''
        self.avatar_path = unsimplify_path(path)
        pixmap = path_to_pixmap(self.avatar_path, diameter=self.diameter, circular=self.circular)
        self.setPixmap(pixmap)
        self.avatarChanged.emit()

    def clear_value(self):
        self.avatar_path = None
        self.setPixmap(path_to_pixmap(None, diameter=self.diameter, circular=self.circular))
        self.avatarChanged.emit()

    def change_avatar(self):
        if not hasattr(self, '_popup'):
            self._popup = _ImageSettingsPopup(self)
        config = {}
        if self.avatar_path:
            config['browse.path'] = self.avatar_path
        self._popup.image_settings.load_config(config)
        self._popup.image_settings.load()
        if self._popup.isVisible():
            self._popup.hide()
        else:
            self._popup.show()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def setPixmap(self, pixmap):
        if not pixmap:  # todo
            return
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                self.diameter, self.diameter,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )
        super().setPixmap(pixmap)
        QTimer.singleShot(1, self.update)  # todo hack for image cutoff bug

    def paintEvent(self, event):
        painter = QPainter()
        if not painter.begin(self):
            super().paintEvent(event)
            return
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addEllipse(0, 0, self.diameter, self.diameter)
        painter.setClipPath(path)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.drawPixmap(0, 0, self.pixmap())
        painter.setCompositionMode(QPainter.CompositionMode_DestinationOver)
        from gui.style import PRIMARY_COLOR
        painter.fillRect(self.rect(), QColor(PRIMARY_COLOR))
        painter.end()
