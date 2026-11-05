"""Condition Settings Widget.

Provides a CEL expression editor for the Condition member type.
"""

from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class ConditionSettings(ConfigJoined):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.widgets = [
            self.ConditionFields(self),
        ]

    class ConditionFields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.schema = [
                {
                    'key': 'expression',
                    'text': 'Expression',
                    'type': str,
                    'num_lines': 4,
                    'stretch_x': True,
                    'stretch_y': True,
                    'highlighter': 'cel',
                    'monospaced': True,
                    'label_position': None,
                    'default': 'true',
                },
            ]
