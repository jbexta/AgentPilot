
from abc import abstractmethod
from PySide6.QtGui import Qt

from src.gui.widgets.config_fields import ConfigFields
from src.gui.widgets.config_json_tree import ConfigJsonTree
from src.gui.widgets.config_tabs import ConfigTabs
from src.gui.widgets.config_pages import ConfigPages
from src.gui.widgets.config_json_db_tree import ConfigJsonDBTree
from src.gui.widgets.config_joined import ConfigJoined
from src.gui.widgets.config_voice_tree import ConfigVoiceTree

from src.gui.util import find_main_widget


class AgentSettings(ConfigPages):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.main = find_main_widget(parent)
        self.layout.addSpacing(10)

        self.pages = {
            'Info': self.Info_Settings(self),
            'Chat': self.Chat_Settings(self),
            # 'Files': self.File_Settings(self),
            'Tools': self.Tool_Settings(self),
        }

    @abstractmethod
    def save_config(self):
        """Saves the config to database when modified"""
        pass

    class Info_Settings(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent, layout_type='vertical')
            self.widgets = [
                self.Info_Fields(parent=self),
            ]

        class Info_Fields(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.conf_namespace = 'info'
                self.field_alignment = Qt.AlignHCenter
                self.schema = [
                    {
                        'text': 'Avatar',
                        'key': 'avatar_path',
                        'type': 'CircularImageLabel',
                        'default': '',
                        'label_position': None,
                    },
                    {
                        'text': 'Name',
                        'type': str,
                        'default': 'Assistant',
                        'stretch_x': True,
                        'text_size': 15,
                        'text_alignment': Qt.AlignCenter,
                        'label_position': None,
                        'transparent': True,
                    },
                    {
                        'text': 'Plugin',
                        'key': 'use_plugin',
                        'type': 'PluginComboBox',
                        'plugin_type': 'AGENT',
                        'label_position': None,
                        'centered': True,
                        'default': '',
                    }
                ]

    class Chat_Settings(ConfigTabs):
        def __init__(self, parent):
            super().__init__(parent=parent)

            self.pages = {
                'Messages': self.Page_Chat_Messages(parent=self),
                'Preload': self.Page_Chat_Preload(parent=self),
                'Group': self.Page_Chat_Group(parent=self),
                'Voice': self.Page_Chat_Voice(parent=self),
            }

        class Page_Chat_Messages(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.conf_namespace = 'chat'
                self.schema = [
                    {
                        'text': 'Model',
                        'type': 'ModelComboBox',
                        'model_kind': 'CHAT',
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
                        'text': 'System message',
                        'key': 'sys_msg',
                        'type': str,
                        'num_lines': 12,
                        'default': '',
                        'stretch_x': True,
                        'enhancement_key': 'system_message',
                        'stretch_y': True,
                        'label_position': 'top',
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
                        'type': 'RoleComboBox',
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

        class Page_Chat_Group(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.conf_namespace = 'group'
                self.label_width = 220
                self.schema = [
                    {
                        'text': 'Output role',
                        'type': 'RoleComboBox',
                        'width': 90,
                        'tooltip': 'Set the primary output role for this member',
                        'default': 'assistant',
                    },
                    {
                        'text': 'Output placeholder',
                        'type': str,
                        # 'stretch_x': True,
                        'tooltip': 'A tag to use this member\'s output from other members system messages',
                        'default': '',
                    },
                    {
                        'text': 'Hide bubbles',
                        'type': bool,
                        'tooltip': 'When checked, the responses from this member will not be shown in the chat',
                        'default': False,
                    },
                    # {
                    #     'text': 'On multiple message inputs',
                    #     'type': ('Use all', 'Use only sender'),  # Append to system msg', 'Merged user message'),  # todo this needs implementing into workflow
                    #     'tooltip': 'How to handle multiple inputs from the user (Not implemented yet)',
                    #     # 'width': 175,
                    #     'default': 'Merged user message',
                    # },
                    {
                        'text': 'Member description',
                        'type': str,
                        'num_lines': 4,
                        'label_position': 'top',
                        'stretch_x': True,
                        'tooltip': 'A description of the member that can be used by other members (Not implemented yet)',
                        'default': '',
                    }
                ]

        class Page_Chat_Voice(ConfigVoiceTree):
            def __init__(self, parent):
                super().__init__(parent=parent)

    # class File_Settings(ConfigJsonFileTree):
    #     def __init__(self, parent):
    #         self.IS_DEV_MODE = True
    #         super().__init__(
    #             parent=parent,
    #             add_item_options={'title': 'NA', 'prompt': 'NA'},
    #             del_item_options={'title': 'NA', 'prompt': 'NA'},
    #             tree_header_hidden=True,
    #             readonly=True
    #         )
    #         self.parent = parent
    #         self.conf_namespace = 'files'
    #         self.schema = [
    #             {
    #                 'text': 'Filename',
    #                 'type': str,
    #                 'width': 175,
    #                 'default': '',
    #             },
    #             {
    #                 'text': 'Location',
    #                 'type': str,
    #                 # 'visible': False,
    #                 'stretch': True,
    #                 'default': '',
    #             },
    #             {
    #                 'text': 'is_dir',
    #                 'type': bool,
    #                 'visible': False,
    #                 'default': False,
    #             },
    #         ]

    class Tool_Settings(ConfigJsonDBTree):
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
