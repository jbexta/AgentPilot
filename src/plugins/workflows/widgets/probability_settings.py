"""Probability Settings Widget.

Provides mode selection (Uniform / Gaussian) with conditional
fields for configuring the Probability member.
"""

from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_joined import ConfigJoined
from utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class ProbabilitySettings(ConfigJoined):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.widgets = [
            self.ProbabilityFields(self),
        ]

    class ProbabilityFields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.schema = [
                {
                    'key': 'mode',
                    'text': 'Mode',
                    'type': ('Uniform', 'Gaussian'),
                    'default': 'Uniform',
                    'width': 120,
                },
                {
                    'key': 'probability',
                    'text': 'Probability (%)',
                    'type': int,
                    'style': 'slider',
                    'minimum': 0,
                    'maximum': 100,
                    'step': 1,
                    'default': 50,
                    'left_label': '0',
                    'right_label': '100',
                    'visibility_predicate': lambda f:
                        f.config.get('mode', 'Uniform') == 'Uniform',
                },
                {
                    'key': 'mean',
                    'text': 'Mean (%)',
                    'type': int,
                    'style': 'slider',
                    'minimum': 0,
                    'maximum': 100,
                    'step': 1,
                    'default': 50,
                    'left_label': '0',
                    'right_label': '100',
                    'visibility_predicate': lambda f:
                        f.config.get('mode', 'Uniform') == 'Gaussian',
                },
                {
                    'key': 'std_dev',
                    'text': 'Spread',
                    'type': int,
                    'style': 'slider',
                    'minimum': 1,
                    'maximum': 50,
                    'step': 1,
                    'default': 15,
                    'left_label': '1',
                    'right_label': '50',
                    'visibility_predicate': lambda f:
                        f.config.get('mode', 'Uniform') == 'Gaussian',
                },
            ]
