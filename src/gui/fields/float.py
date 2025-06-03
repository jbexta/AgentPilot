from PySide6.QtWidgets import QDoubleSpinBox



class Float(QDoubleSpinBox):
    def __init__(self, parent, **kwargs):
        super().__init__(parent)
        minimum = kwargs.get('minimum', -1.7976931348623157e+308)
        maximum = kwargs.get('maximum', 1.7976931348623157e+308)
        step = kwargs.get('step', 0.05)
        self.setRange(minimum, maximum)
        self.setSingleStep(step)
        self.valueChanged.connect(parent.update_config)

    def set_value(self, value):
        self.setValue(value)

    def get_value(self):
        return self.value()

    def clear_value(self):
        self.setValue(0.0)