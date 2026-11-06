from PySide6.QtGui import Qt
from PySide6.QtWidgets import QDoubleSpinBox, QSlider, QWidget

from gui.gui_utils.layouts import CVBoxLayout


class Float(QWidget):
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

        self.layout = CVBoxLayout(self)
        self.is_slider = kwargs.get('style', 'spinbox') == 'slider'
        if self.is_slider:
            # QSlider is int only, so it counts steps
            self.step = step
            self.inner_widget = QSlider(Qt.Horizontal, parent)
            self.inner_widget.setProperty('class', 'int-slider')
            self.inner_widget.setRange(round(minimum / step), round(maximum / step))
        else:
            self.inner_widget = QDoubleSpinBox(parent)
            self.inner_widget.setDecimals(kwargs.get('decimals', 2))
            self.inner_widget.setRange(minimum, maximum)
            self.inner_widget.setSingleStep(step)
        self.layout.addWidget(self.inner_widget)

        self.inner_widget.valueChanged.connect(parent.update_config)
        self.inner_widget.wheelEvent = lambda e: e.ignore()

    def get_value(self):
        if self.is_slider:
            return round(self.inner_widget.value() * self.step, 10)
        return self.inner_widget.value()

    def set_value(self, value):
        if not isinstance(value, float):
            try:
                value = float(str(value))
            except (ValueError, TypeError):
                value = 0.0
        if self.is_slider:
            value = round(value / self.step)
        self.inner_widget.setValue(value)  # not recursive, camelCase not snake_case

    def clear_value(self):
        self.inner_widget.setValue(0)
