from gui.widgets.config_fields import ConfigFields
from plugins.workflows.managers.models import LIVE_MODELS


class LiveAgentSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.conf_namespace = 'live'
        self.schema = [
            {
                'text': 'Model',
                'type': 'model',
                'model_kind': 'CHAT',
                'model_names': LIVE_MODELS,
                'popup_params': True,
                'width': 200,
                'default': '',
                'tooltip': 'A GPT-Live model. Voice, delegation and backend model are in its options.',
            },
            {
                'text': 'System message',
                'key': 'sys_msg',
                'type': str,
                'num_lines': 12,
                'default': '',
                'stretch_x': True,
                'stretch_y': True,
                'label_position': 'top',
            },
        ]
