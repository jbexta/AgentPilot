
"""Code Block Settings Widget Module.

This module provides the CodeBlockSettings widget, a specialized configuration
interface for code block components in Agent Pilot workflows. It manages the
configuration of code execution blocks with schema-driven field generation.

Key Features:
- Schema-driven configuration fields for code blocks
- Integration with the configuration fields system
- Specialized settings for code execution parameters
- Plugin-based block type selection
- Workflow block configuration management

The CodeBlockSettings widget provides a dedicated interface for configuring
code execution blocks within Agent Pilot workflows, ensuring proper parameter
setup and execution configuration.
"""  # unchecked

from gui.widgets.config_fields import ConfigFields


class CodeSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema = [
            # # {
            # #     'text': 'Type',
            # #     'key': '_TYPE',
            # #     'type': 'PluginComboBox',
            # #     'plugin_type': 'BLOCK',
            # #     'allow_none': False,
            # #     'width': 90,
            # #     'default': 'Text',
            # #     'row_key': 0,
            # # },
            # {
            #     'text': 'Type',
            #     'key': '_TYPE',
            #     'type': 'module',
            #     'module_type': 'Members',
            #     'items_have_keys': False,
            #     'default': 'Default',
            #     'row_key': 0,
            # },
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
            # {
            #     'text': 'Member options',
            #     'type': 'popup_button',
            #     'use_namespace': 'group',
            #     'member_type': 'code',
            #     'label_position': None,
            #     'default': '',
            #     'row_key': 0,
            # },
            {
                'text': 'Data',
                'type': str,
                'default': '',
                'num_lines': 2,
                'stretch_x': True,
                'stretch_y': True,
                'highlighter': 'python',
                'fold_mode': 'python',
                'monospaced': True,
                'label_position': None,
            },
        ]
