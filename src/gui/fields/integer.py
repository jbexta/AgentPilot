from PySide6.QtWidgets import QSpinBox


class Integer(QSpinBox):
    def __init__(self, parent, **kwargs):
        super().__init__(parent)
        minimum = kwargs.get('minimum', -2147483648)
        maximum = kwargs.get('maximum', 2147483647)
        step = kwargs.get('step', 1)
        self.setRange(minimum, maximum)
        self.setSingleStep(step)
        self.valueChanged.connect(parent.update_config)

    def set_value(self, value):
        self.setValue(value)

    def get_value(self):
        return self.value()

    def clear_value(self):
        self.setValue(0)