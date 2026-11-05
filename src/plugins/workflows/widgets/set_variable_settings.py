from gui.widgets.config_fields import ConfigFields
from utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class SetVariableSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema = [
            {
                'text': 'Variable',
                'key': 'variable',
                'type': str,
                'default': '',
                'width': 200,
            },
            {
                'text': 'Value',
                'key': 'value',
                'type': str,
                'default': '',
                'num_lines': 4,
                'stretch_x': True,
                'stretch_y': True,
                'label_position': 'top',
            },
        ]
