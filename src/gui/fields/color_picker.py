from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, Qt
from PySide6.QtWidgets import QColorDialog, QPushButton

from src.utils.helpers import block_pin_mode, apply_alpha_to_hex


class ColorPickerWidget(QPushButton):
    colorChanged = Signal(str)

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        from src.gui.style import TEXT_COLOR
        self.color = None
        # self.setFixedSize(24, 24)
        self.setFixedWidth(24)
        self.setProperty('class', 'color-picker')
        self.setStyleSheet(f"background-color: white; border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.20)};")
        self.clicked.connect(self.pick_color)
        self.colorChanged.connect(parent.update_config)

    def pick_color(self):
        from src.gui.style import TEXT_COLOR
        current_color = self.color if self.color else Qt.white
        color_dialog = QColorDialog()
        with block_pin_mode():
            # show alpha channel
            color = color_dialog.getColor(current_color, parent=self, options=QColorDialog.ShowAlphaChannel)

        if color.isValid():
            self.color = color
            self.setStyleSheet(f"background-color: {color.name(QColor.HexArgb)}; border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.20)};")
            self.colorChanged.emit(color.name(QColor.HexArgb))

    def set_value(self, hex_color):
        from src.gui.style import TEXT_COLOR
        color = QColor(hex_color)
        if color.isValid():
            self.color = color
            self.setStyleSheet(f"background-color: {color.name(QColor.HexArgb)}; border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.20)};")

    def get_color(self):
        return self.color.name(QColor.HexArgb) if self.color and self.color.isValid() else None

    def clear_value(self):
        self.set_value('#FFFFFF')
