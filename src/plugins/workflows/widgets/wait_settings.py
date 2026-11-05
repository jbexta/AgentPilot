from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class WaitSettings(ConfigJoined):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.widgets = [
            self.WaitFields(self),
        ]

    class WaitFields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.schema = [
                {
                    'key': 'duration',
                    'text': 'Duration (s)',
                    'type': int,
                    'minimum': 0,
                    'maximum': 3600,
                    'step': 1,
                    'default': 5,
                },
            ]