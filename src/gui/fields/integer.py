from PySide6.QtWidgets import QSpinBox


class Integer(QSpinBox):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.setRange(-2147483648, 2147483647)  # Set range for 32-bit signed integer
        self.valueChanged.connect(parent.update_config)

    def set_value(self, value):
        self.setValue(value)

    def clear_value(self):
        self.setValue(0)