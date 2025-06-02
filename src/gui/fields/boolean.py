from PySide6.QtWidgets import QCheckBox


class Boolean(QCheckBox):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.stateChanged.connect(parent.update_config)

    def set_value(self, value):
        self.setChecked(value)

    def clear_value(self):
        self.setChecked(False)
