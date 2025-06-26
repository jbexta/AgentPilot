from src.gui.util import ToggleIconButton


class ButtonToggle(ToggleIconButton):
    def __init__(self, parent, **kwargs):
        # kwargs.pop('text', None)  # Remove 'text' argument if it exists
        super().__init__(parent=parent, **kwargs)
        # connect checked signal to the value change
        self.toggled.connect(parent.update_config)

    def get_value(self):
        return self.isChecked()

    def set_value(self, value):
        self.setChecked(value)
