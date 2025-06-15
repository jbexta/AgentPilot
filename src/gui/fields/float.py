from PySide6.QtWidgets import QDoubleSpinBox



class Float(QDoubleSpinBox):
    option_schema = [
        {
            'text': 'Minimum',
            'key': 'f_minimum',
            'type': float,
            'minimum': -3.402823466e+38,
            'maximum': 3.402823466e+38,
            'step': 0.1,
            'default': 0.0,
        },
        {
            'text': 'Maximum',
            'key': 'f_maximum',
            'type': float,
            'minimum': -3.402823466e+38,
            'maximum': 3.402823466e+38,
            'step': 0.1,
            'default': 1.0,
        },
        {
            'text': 'Step',
            'key': 'f_step',
            'type': float,
            'minimum': -3.402823466e+38,
            'maximum': 3.402823466e+38,
            'step': 0.1,
            'default': 0.1,
        }
    ]

    def __init__(self, parent, **kwargs):
        super().__init__(parent)
        minimum = kwargs.get('minimum', -1.7976931348623157e+308)
        maximum = kwargs.get('maximum', 1.7976931348623157e+308)
        step = kwargs.get('step', 0.05)
        self.setRange(minimum, maximum)
        self.setSingleStep(step)
        self.valueChanged.connect(parent.update_config)

    def set_value(self, value):
        if not isinstance(value, float):
            try:
                value = float(str(value))
            except (ValueError, TypeError):
                value = 0.0
        self.setValue(value)

    def get_value(self):
        return self.value()

    def clear_value(self):
        self.setValue(0.0)