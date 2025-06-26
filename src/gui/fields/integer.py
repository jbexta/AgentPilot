from PySide6.QtWidgets import QSpinBox


class Integer(QSpinBox):
    option_schema = [
        {
            'text': 'Minimum',
            'key': 'f_minimum',
            'type': int,
            'minimum': -2147483647,
            'maximum': 2147483647,
            'step': 5,
            'default': 0,
        },
        {
            'text': 'Maximum',
            'key': 'f_maximum',
            'type': int,
            'minimum': -2147483647,
            'maximum': 2147483647,
            'step': 5,
            'default': 100,
        },
        {
            'text': 'Step',
            'key': 'f_step',
            'type': int,
            'minimum': -2147483647,
            'maximum': 2147483647,
            'step': 1,
            'default': 1,
        }
    ]

    def __init__(self, parent, **kwargs):
        super().__init__(parent)
        minimum = kwargs.get('minimum', -2147483648)
        maximum = kwargs.get('maximum', 2147483647)
        step = kwargs.get('step', 1)
        self.setRange(minimum, maximum)
        self.setSingleStep(step)
        self.valueChanged.connect(parent.update_config)

    def get_value(self):
        return self.value()

    def set_value(self, value):
        if not isinstance(value, int):  # todo clean
            try:
                value = int(str(value))
            except (ValueError, TypeError):
                value = 0
        self.setValue(value)  # not recursive, camelCase not snake_case

    def clear_value(self):
        self.setValue(0)