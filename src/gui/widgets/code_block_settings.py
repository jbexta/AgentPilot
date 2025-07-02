
from gui.widgets.config_fields import ConfigFields


class CodeBlockSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema = [
            # {
            #     'text': 'Type',
            #     'key': '_TYPE',
            #     'type': 'PluginComboBox',
            #     'plugin_type': 'BLOCK',
            #     'allow_none': False,
            #     'width': 90,
            #     'default': 'Text',
            #     'row_key': 0,
            # },
            {
                'text': 'Type',
                'key': '_TYPE',
                'type': 'module',
                'module_type': 'Members',
                'items_have_keys': False,
                'default': 'Default',
                'row_key': 0,
            },
            {
                'text': 'Language',
                'type':
                ('AppleScript', 'HTML', 'JavaScript', 'Python', 'PowerShell', 'R', 'React', 'Ruby', 'Shell',),
                'width': 100,
                'tooltip': 'The language of the code to be passed to open interpreter',
                'label_position': None,
                'row_key': 0,
                'default': 'Python',
            },
            {
                'text': '',
                'key': 'environment',
                'type': 'combo',
                'table_name': 'environments',
                'fetch_keys': ('name', 'id',),
                'width': 90,
                'default': 'Local',
                'row_key': 0,
            },
            {
                'text': 'Member options',
                'type': 'popup_button',
                'use_namespace': 'group',
                'member_type': 'code_block',
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
                'highlighter': 'PythonHighlighter',
                'fold_mode': 'python',
                'monospaced': True,
                'label_position': None,
            },
        ]
