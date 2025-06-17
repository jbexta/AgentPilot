
from src.gui.widgets.config_fields import ConfigFields
from src.gui.widgets.config_joined import ConfigJoined
from src.utils.helpers import set_module_type, mini_avatar


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
                    'text': 'Color',
                    'type': 'color_picker',
                    'default': '#438BB9',
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

    # @mini_avatar('btn_rerun')
    # class RerunButton(MessageButton):