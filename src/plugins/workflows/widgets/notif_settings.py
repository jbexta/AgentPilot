from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class NotifSettings(ConfigJoined):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.widgets = [
            self.NotifFields(self),
        ]

    class NotifFields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.schema = [
                {
                    'text': 'Icon',
                    'type': ('NoIcon', 'Information', 'Warning', 'Critical'),
                    'default': 'Information',
                    'row_key': 0,
                },
                {
                    'text': 'Duration (ms)',
                    'key': 'duration',
                    'type': int,
                    'default': 5000,
                    'row_key': 0,
                },
                {
                    'text': 'Title',
                    'type': str,
                    'has_toggle': True,
                    'default': '',
                    'row_key': 1,
                },
                {
                    'text': 'Color',
                    'type': 'color_picker',
                    'default': '#438BB9',
                    'row_key': 1,
                },
                {
                    'text': 'Text',
                    'type': str,
                    'default': '',
                    'num_lines': 4,
                    'stretch_x': True,
                    'stretch_y': True,
                    'label_position': 'top',
                },
            ]
            