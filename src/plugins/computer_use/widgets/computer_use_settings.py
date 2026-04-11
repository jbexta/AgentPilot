"""Computer Use settings widget."""

from gui.widgets.config_fields import ConfigFields


class ComputerUseSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.conf_namespace = 'computer_use'
        self.schema = [
            {
                'text': 'Enabled',
                'type': bool,
                'default': False,
            },
            {
                'text': 'Grace period',
                'type': float,
                'minimum': 0.0,
                'maximum': 10.0,
                'step': 0.5,
                'default': 3.0,
                'width': 75,
                'row_key': 'A',
            },
            {
                'text': 'Max iterations',
                'type': int,
                'minimum': 1,
                'maximum': 200,
                'default': 50,
                'width': 75,
                'row_key': 'A',
            },
        ]
