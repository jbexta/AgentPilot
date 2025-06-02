from PySide6.QtWidgets import QDoubleSpinBox


class Float(QDoubleSpinBox):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.setRange(-1.7976931348623157e+308, 1.7976931348623157e+308)  # Set range for double
        self.valueChanged.connect(parent.update_config)

    def set_value(self, value):
        self.setValue(value)

    def clear_value(self):
        self.setValue(0.0)