
from gui.widgets.config_fields import ConfigFields


class TextBlockSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema = [
            {
                'text': 'Type',
                'key': '_TYPE',
                'type': 'PluginComboBox',
                'plugin_type': 'BLOCK',
                'allow_none': False,
                'width': 90,
                'default': 'Text',
                'row_key': 0,
            },
            {
                'text': 'Member options',
                'type': 'popup_button',
                'use_namespace': 'group',
                'member_type': 'text_block',
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



# @set_module_type(module_type='Widgets')
# class ModuleBlockSettings(ConfigJoined):
#     def __init__(self, parent):
#         super().__init__(parent=parent)
#         self.widgets = [
#             self.ModuleFields(parent=self),
#             self.ModuleTargetPlugin(parent=self),
#         ]
#
#     class ModuleFields(ConfigFields):
#         def __init__(self, parent):
#             super().__init__(parent=parent)
#             # self.label_width = 100
#             self.schema = [
#                 {
#                     'text': 'Type',
#                     'key': '_PLUGIN',
#                     'type': 'PluginComboBox',
#                     'plugin_type': 'BLOCK',
#                     'allow_none': False,
#                     'width': 90,
#                     'default': 'Text',
#                     'row_key': 0,
#                 },
#                 {
#                     'text': 'Module',
#                     'type': 'ModuleComboBox',
#                     'label_position': None,
#                     'default': 'Select a module',
#                     'row_key': 0,
#                 },
#                 {
#                     'text': 'Member options',
#                     'type': 'MemberPopupButton',
#                     'use_namespace': 'group',
#                     'member_type': 'block',
#                     'label_position': None,
#                     'default': '',
#                     'row_key': 0,
#                 },
#                 # {
#                 #     'text': 'Target',
#                 #     'key': 'target',
#                 #     'type': ('Attribute', 'Method',),
#                 #     'width': 90,
#                 #     # 'label_position': None,
#                 #     'default': 'Method',
#                 # },
#             ]
#
#     class ModuleTargetPlugin(ConfigPlugin):
#         def __init__(self, parent):
#             super().__init__(
#                 parent,
#                 plugin_type='ModuleTargetSettings',
#                 plugin_json_key='target',
#                 plugin_label_text='Target',
#             )
#
#
# class ModuleMethodSettings(ConfigFields):
#     def __init__(self, parent):
#         super().__init__(parent=parent, conf_namespace='method')
#         self.schema = [
#             {
#                 'text': 'Data',
#                 'type': str,
#                 'default': '',
#                 'num_lines': 2,
#                 'stretch_x': True,
#                 'stretch_y': True,
#                 'label_position': None,
#             },
#         ]
#
# class ModuleVariableSettings(ConfigFields):
#     def __init__(self, parent):
#         super().__init__(parent=parent, conf_namespace='variable')
#         self.schema = [
#             {
#                 'text': 'Data',
#                 'type': str,
#                 'default': '',
#                 'num_lines': 2,
#                 'stretch_x': True,
#                 'stretch_y': True,
#                 'label_position': None,
#             },
#         ]
#
#
# class ModuleToolSettings(ConfigFields):
#     def __init__(self, parent):
#         super().__init__(parent=parent, conf_namespace='tool')
#         self.schema = [
#             {
#                 'text': 'Data',
#                 'type': str,
#                 'default': '',
#                 'num_lines': 2,
#                 'stretch_x': True,
#                 'stretch_y': True,
#                 'label_position': None,
#             },
#         ]
#
