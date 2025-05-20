
from src.gui.widgets import ConfigFields
from src.utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class ImageModelSettings(ConfigFields):
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
                'model_kind': 'IMAGE',
                # 'default': 'mistral/mistral-large-latest',
                'row_key': 0,
            },
            # {
            #     'text': 'Member options',
            #     'type': 'MemberPopupButton',
            #     'use_namespace': 'group',
            #     'member_type': 'image',
            #     'label_position': None,
            #     'default': '',
            #     'row_key': 0,
            # },
        ]