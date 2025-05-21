
from src.gui.widgets.config_fields import ConfigFields


class PromptBlockSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema = [
            {
                'text': 'Type',
                'key': '_PLUGIN',
                'type': 'PluginComboBox',
                'plugin_type': 'BLOCK',
                'allow_none': False,
                'width': 90,
                'default': 'Text',
                'row_key': 0,
            },
            {
                'text': 'Model',
                'key': 'prompt_model',
                'type': 'ModelComboBox',
                'model_kind': 'CHAT',
                'label_position': None,
                'default': 'default',
                'row_key': 0,
            },
            {
                'text': 'Member options',
                'type': 'MemberPopupButton',
                'use_namespace': 'group',
                'member_type': 'block',
                'label_position': None,
                'default': '',
                'row_key': 0,
            },
            {
                'text': 'Data',
                'type': str,
                'default': '',
                'num_lines': 2,
                'stretch_x': True,
                'stretch_y': True,
                'highlighter': 'XMLHighlighter',
                'fold_mode': 'xml',
                'label_position': None,
            },
        ]