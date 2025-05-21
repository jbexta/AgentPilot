
from src.gui.widgets.config_fields import ConfigFields


class VoiceModelSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema = [
            {
                'text': 'Type',
                'key': 'model_type',
                'type': 'PluginComboBox',
                'plugin_type': 'MODEL',
                'allow_none': False,
                'width': 90,
                'default': 'Voice',
                'row_key': 0,
            },
            {
                'text': 'Model',
                'type': 'ModelComboBox',
                'model_kind': 'VOICE',
                # 'default': 'mistral/mistral-large-latest',
                'default': {
                    'kind': 'VOICE',
                    'model_name': '9BWtsMINqrJLrRacOk9x',
                    # 'model_params': {},
                    'provider': 'elevenlabs',
                },
                'row_key': 0,
            },
            {
                'text': 'Text',
                'type': str,
                'label_position': 'top',
                'num_lines': 3,
                'stretch_x': True,
                'stretch_y': True,
                'default': '',
            },
            {
                'text': 'Play audio',
                'type': bool,
                'default': True,
                'row_key': 1,
            },
            {
                'text': 'Use cache',
                'type': bool,
                'default': False,
                'row_key': 1,
            },
            {
                'text': 'Wait until finished',
                'type': bool,
                'default': False,
                'row_key': 1,
            },
            # {
            #     'text': 'Member options',
            #     'type': 'MemberPopupButton',
            #     'use_namespace': 'group',
            #     'member_type': 'voice',
            #     'label_position': None,
            #     'default': '',
            #     'row_key': 0,
            # },
        ]

