from PySide6.QtCore import Signal
from PySide6.QtGui import Qt, QPainter, QPainterPath
from PySide6.QtWidgets import QLabel, QFileDialog

from src.utils.filesystem import unsimplify_path
from src.utils.helpers import path_to_pixmap, block_pin_mode


class Image(QLabel):
    clicked = Signal()
    avatarChanged = Signal()

    def __init__(self, parent=None, **kwargs):  # *args, diameter=50, **kwargs):
        super().__init__(parent)
        self.avatar_path = None
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.diameter = kwargs.get('diameter', 50)
        self.circular = kwargs.get('circular', True)
        border = kwargs.get('border', True)
        from src.gui.style import TEXT_COLOR
        border_ss = f"border: 1px dashed {TEXT_COLOR};" if border else ""
        radius = int(self.diameter / 2) if self.circular else 0
        circular_ss = f"border-radius: {str(radius)}px;"
        self.setStyleSheet(
            f"{border_ss} {circular_ss} background-color: transparent;")
        self.setFixedSize(self.diameter, self.diameter)
        self.clicked.connect(self.change_avatar)
        self.avatarChanged.connect(parent.update_config)

        # radius = int(diameter / 2)
        # self.setFixedSize(diameter, diameter)
        # self.setStyleSheet(
        #     f"border: 1px dashed {TEXT_COLOR}; border-radius: {str(radius)}px;")
        # self.clicked.connect(self.change_avatar)
        # self.avatarChanged.connect(parent.update_config)

    def set_value(self, path):
        self.avatar_path = unsimplify_path(path)
        pixmap = path_to_pixmap(self.avatar_path, diameter=self.diameter, circular=self.circular)
        self.setPixmap(pixmap)
        self.avatarChanged.emit()

    def get_value(self):
        return self.avatar_path

    def change_avatar(self):
        with block_pin_mode():
            fd = QFileDialog()
            fd.setOption(QFileDialog.DontUseNativeDialog, True)
            fd.setStyleSheet("QFileDialog { color: black; }")  # Modify text color
            filename, _ = fd.getOpenFileName(None, "Choose Avatar", "",
                                                        "Images (*.png *.jpeg *.jpg *.bmp *.gif *.webp)", options=QFileDialog.Options())

        if filename:
            self.set_value(filename)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def setPixmap(self, pixmap):
        if not pixmap:  # todo
            return
        super().setPixmap(pixmap.scaled(
            self.width(), self.height(),
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation
        ))

    def paintEvent(self, event):
        # Override paintEvent to draw a circular image
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addEllipse(0, 0, self.width(), self.height())
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, self.pixmap())
        painter.end()
