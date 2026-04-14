from PySide6.QtGui import Qt
from PySide6.QtWidgets import QSlider, QSpinBox, QWidget, QLabel

from gui.style import ACCENT_COLOR_1
from gui.util import CVBoxLayout, CHBoxLayout
from utils.helpers import apply_alpha_to_hex


class Integer(QWidget):
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
        },
        {
            'text': 'Left Label',
            'key': 'f_left_label',
            'type': str,
            'default': '',
            'tooltip': 'Label to display on the left side of the slider',
        },
        {
            'text': 'Right Label',
            'key': 'f_right_label',
            'type': str,
            'default': '',
            'tooltip': 'Label to display on the right side of the slider',
        },
        {
            'text': 'Show Slider Fill',
            'key': 'f_show_slider_fill',
            'type': bool,
            'default': True,
            'tooltip': 'Show the blue fill bar on the slider when style is "slider"',
        },
        {
            'text': 'Slider Snap To',
            'key': 'f_slider_snap_to',
            'type': int,
            'minimum': 0,
            'maximum': 1000,
            'step': 1,
            'default': 0,
            'tooltip': 'Value interval to snap slider to (0 = no snapping). Only applies when style is "slider"',
        }
    ]

    def __init__(self, parent, **kwargs):
        super().__init__(parent)
        self.parent = parent  # Store parent for update_config callback
        style = kwargs.get('style', 'spinbox')  # slider / spinbox
        orientation = kwargs.get('orientation', Qt.Horizontal)
        minimum = max(kwargs.get('minimum', -2147483647), -2147483647)
        maximum = min(kwargs.get('maximum', 2147483647), 2147483647)
        step = kwargs.get('step', 1)
        left_label = kwargs.get('left_label', '')
        right_label = kwargs.get('right_label', '')
        show_slider_fill = kwargs.get('show_slider_fill', True)
        slider_snap_to = kwargs.get('slider_snap_to', 0)

        self.layout = CVBoxLayout(self)
        self.inner_widget = None
        self.snap_to = slider_snap_to  # Store snap_to value for later use
        self._is_snapping = False  # Flag to prevent recursive snapping

        if style == 'slider':
            # Create slider with optional labels
            self.inner_widget = QSlider(parent)
            self.inner_widget.setOrientation(orientation)
            self.inner_widget.setContentsMargins(0, 0, 0, 0)

            # If snap_to is specified, connect to handle snapping
            if slider_snap_to > 0:
                # Snap during dragging for better UX
                self.inner_widget.valueChanged.connect(self._handle_value_changed)

            # # Apply stylesheet to hide/show the fill bar (sub-page)
            from gui.style import TEXT_COLOR
            orientation_style = 'horizontal' if orientation == Qt.Horizontal else 'vertical'
            fill_color = apply_alpha_to_hex(ACCENT_COLOR_1, 0.6) if show_slider_fill else 'transparent'
            self.inner_widget.setStyleSheet(f"""
                QSlider::groove:{orientation_style} {{
                    border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.3)};
                    height: 8px;
                    background: {apply_alpha_to_hex(TEXT_COLOR, 0.1)};
                    border-radius: 2px;
                }}
                QSlider::handle:{orientation_style} {{
                    background: {apply_alpha_to_hex(TEXT_COLOR, 0.5)};
                    border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.6)};
                    width: 8px;
                    border-radius: 2px;
                }}
                QSlider::handle:{orientation_style}:hover {{
                    background: {apply_alpha_to_hex(TEXT_COLOR, 0.7)};
                    border: 1px solid {apply_alpha_to_hex(TEXT_COLOR, 0.8)};
                }}
                QSlider::sub-page:{orientation_style} {{
                    background: {fill_color};
                    border: none;
                }}
                QSlider::add-page:{orientation_style} {{
                    background: none;
                    border: none;
                }}
            """)

            # If labels are provided, create a horizontal layout with labels
            if left_label or right_label:
                slider_container = QWidget()
                slider_layout = CHBoxLayout(slider_container)

                if left_label:
                    left_label_widget = QLabel(left_label)
                    left_label_widget.setFixedWidth(18)
                    left_label_widget.setStyleSheet("font-size: 10px;")
                    slider_layout.addWidget(left_label_widget)

                slider_layout.addWidget(self.inner_widget, stretch=1)

                if right_label:
                    right_label_widget = QLabel(right_label)
                    right_label_widget.setFixedWidth(18)
                    right_label_widget.setStyleSheet("font-size: 10px;")
                    slider_layout.addWidget(right_label_widget)

                self.layout.addWidget(slider_container)
            else:
                self.layout.addWidget(self.inner_widget)
        elif style == 'spinbox':
            self.inner_widget = QSpinBox(parent)
            self.layout.addWidget(self.inner_widget)
        
        width = kwargs.get('width', None)
        if width:
            self.inner_widget.setFixedWidth(width)

        self.inner_widget.setRange(minimum, maximum)
        self.inner_widget.setSingleStep(step)
        self.inner_widget.valueChanged.connect(parent.update_config)
        self.inner_widget.wheelEvent = lambda e: e.ignore()

    def _handle_value_changed(self, value):
        """Handle value changes for live snapping during drag."""
        if self.snap_to > 0 and not self._is_snapping:
            snapped_value = self._calculate_snapped_value(value)
            if snapped_value != value:
                self._is_snapping = True
                self.inner_widget.setValue(snapped_value)
                self._is_snapping = False
                # Manually trigger the parent's update_config since we're changing the value
                if hasattr(self.parent, 'update_config'):
                    self.parent.update_config()

    def _calculate_snapped_value(self, value):
        """Calculate the snapped value based on snap_to interval."""
        if self.snap_to <= 0:
            return value
        # Round to nearest snap_to interval
        remainder = value % self.snap_to
        if remainder < self.snap_to / 2:
            return value - remainder
        else:
            return value + (self.snap_to - remainder)

    def get_value(self):
        return self.inner_widget.value()
    
    def set_value(self, value):
        if not isinstance(value, int):  # todo clean
            try:
                value = int(str(value))
            except (ValueError, TypeError):
                # raise ValueError(f"Invalid value: {value}")
                print(f"Integer.set_value(): Invalid value: {value}")
                return
        # Clamp to the widget's range to avoid OverflowError
        value = max(self.inner_widget.minimum(),
                    min(value, self.inner_widget.maximum()))
        self.inner_widget.setValue(value)  # not recursive, camelCase not snake_case
    
    def clear_value(self):
        self.inner_widget.setValue(0)