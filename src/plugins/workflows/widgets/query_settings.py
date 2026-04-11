"""Query Settings Widget.

Provides method selection (Execute / Get scalar / Get results) with
a conditional return_type dropdown for configuring the Query member.
"""

from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class QuerySettings(ConfigJoined):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.widgets = [
            self.QueryFields(self),
        ]

    class QueryFields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.schema = [
                {
                    'text': 'Method',
                    'key': 'method',
                    'type': (
                        'Execute',
                        'Scalar',
                        'Results',
                    ),
                    'default': 'Results',
                    'width': 120,
                },
                {
                    'text': 'Query',
                    'key': 'query',
                    'type': str,
                    'num_lines': 6,
                    'stretch_x': True,
                    'stretch_y': True,
                    'label_position': 'top',
                    'placeholder': 'SELECT ...',
                },
                {
                    'text': 'Return type',
                    'key': 'return_type',
                    'type': (
                        'Rows',
                        'List',
                        'Dict',
                        'Hdict',
                        'Tuple',
                    ),
                    'default': 'Rows',
                    'width': 120,
                    'visibility_predicate': lambda f:
                        f.config.get('method') == 'Results',
                },
            ]
