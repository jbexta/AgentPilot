
"""Agent Settings Widget Module.

This module provides the AgentSettings widget, a comprehensive tabbed interface
for configuring AI agents in Agent Pilot. It organizes agent configuration into
multiple specialized pages covering all aspects of agent behavior, from message
handling to voice integration.

Key Features:
- Multi-page tabbed interface for agent configuration
- Message configuration with model selection and parameters
- Preload settings for agent initialization
- Tool integration and management
- Group chat configuration for multi-agent scenarios
- Voice integration settings and configuration
- Schema-driven configuration with validation
- Real-time configuration updates and persistence

The AgentSettings widget serves as the primary interface for defining agent
behavior, capabilities, and integration settings, providing a structured
approach to agent configuration management.
"""  # unchecked

from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_json_tree import ConfigJsonTree
from gui.widgets.config_tabs import ConfigTabs
from gui.widgets.config_json_db_tree import ConfigJsonDBTree
from plugins.computer_use.widgets.computer_use_settings import ComputerUseSettings


class AgentSettings(ConfigTabs):
    def __init__(self, parent):
        super().__init__(parent=parent)

        self.pages = {
            'Messages': self.Page_Chat_Messages(parent=self),
            'Preload': self.Page_Chat_Preload(parent=self),
            'Tools': self.Page_Chat_Tools(parent=self),
            'Computer Use': ComputerUseSettings(parent=self),
            'Voice': self.Page_Chat_Voice(parent=self),
        }

    class Page_Chat_Messages(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.conf_namespace = 'chat'
            self.schema = [
                {
                    'text': 'Model',
                    'type': 'model',
                    'model_kind': 'CHAT',
                    'popup_params': True,
                    'width': 200,
                    'default': '',
                    'row_key': 0,
                },
                {
                    'text': 'Display markdown',
                    'type': bool,
                    'default': True,
                    'row_key': 0,
                },
                {
                    'text': 'Max messages',
                    'type': int,
                    'minimum': 1,
                    'maximum': 99,
                    'default': 10,
                    'width': 60,
                    'has_toggle': True,
                    'row_key': 1,
                },
                {
                    'text': 'Max turns',
                    'type': int,
                    'minimum': 1,
                    'maximum': 99,
                    'default': 7,
                    'width': 60,
                    'has_toggle': True,
                    'row_key': 1,
                },
                {
                    'text': 'System message',
                    'key': 'sys_msg',
                    'type': str,
                    'num_lines': 12,
                    'default': '',
                    'stretch_x': True,
                    'stretch_y': True,
                    'wrap_text': True,
                    'highlighter': 'xml',
                    'fold_mode': 'xml',
                    'format_blocks': True,
                    'enhancement_key': 'system_message',
                    'label_position': 'top',
                },
            ]

    class Page_Chat_Preload(ConfigJsonTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                add_item_options={'title': 'NA', 'prompt': 'NA'},
                del_item_options={'title': 'NA', 'prompt': 'NA'}
            )
            self.conf_namespace = 'chat.preload'
            self.schema = [
                {
                    'text': 'Role',
                    'type': 'combo',
                    'table_name': 'roles',
                    'width': 120,
                    'default': 'assistant',
                },
                {
                    'text': 'Content',
                    'type': str,
                    'stretch': True,
                    'wrap_text': True,
                    'default': '',
                },
                {
                    'text': 'Type',
                    'type': ('Normal', 'Context', 'Welcome'),
                    'width': 90,
                    'default': 'Normal',
                },
            ]

    class Page_Chat_Tools(ConfigJsonDBTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                add_item_options={'title': 'NA', 'prompt': 'NA'},
                del_item_options={'title': 'NA', 'prompt': 'NA'},
                tree_header_hidden=True,
                table_name='tools',
                key_field='uuid',
                item_icon_path=':/resources/icon-tool-small.png',
                show_fields=[
                    'name',
                    'uuid',  # ID ALWAYS LAST
                ],
                readonly=True
            )
            self.conf_namespace = 'tools'
            self.schema = [
                {
                    'text': 'Tool',
                    'type': str,
                    'width': 175,
                    'default': '',
                },
                {
                    'text': 'id',
                    'visible': False,
                    'default': '',
                },
            ]


    class Page_Chat_Variables(ConfigJsonTree):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                add_item_options={'title': 'NA', 'prompt': 'NA'},
                del_item_options={'title': 'NA', 'prompt': 'NA'}
            )
            self.conf_namespace = 'blocks'
            self.schema = [
                {
                    'text': 'Placeholder',
                    'type': str,
                    'width': 120,
                    'default': '< Placeholder >',
                },
                {
                    'text': 'Value',
                    'type': str,
                    'stretch': True,
                    'wrap_text': True,
                    'default': '',
                },
            ]

    class Page_Chat_Voice(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.conf_namespace = 'voice'
            self.schema = [
                {
                    'text': 'Model',
                    'type': 'model',
                    'model_kind': 'AUDIO',
                    'width': 200,
                    'default': '',
                },
            ]
