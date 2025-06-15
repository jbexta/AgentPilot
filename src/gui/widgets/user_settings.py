
from PySide6.QtGui import Qt
from src.gui.widgets.config_fields import ConfigFields
from src.gui.widgets.config_tabs import ConfigTabs
from src.gui.widgets.config_pages import ConfigPages
from src.utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class UserSettings(ConfigPages):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.layout.addSpacing(10)
        self.member_id = None

        self.pages = {
            'Info': self.Info_Settings(self),
            'Chat': self.Chat_Settings(self),
        }

    class Info_Settings(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.conf_namespace = 'info'
            self.field_alignment = Qt.AlignHCenter
            self.schema = [
                {
                    'text': 'Avatar',
                    'key': 'avatar_path',
                    'type': 'image',
                    'default': '',
                    'label_position': None,
                },
                {
                    'text': 'Name',
                    'type': str,
                    'default': 'You',
                    'stretch_x': True,
                    'text_size': 15,
                    'text_alignment': Qt.AlignCenter,
                    'label_position': None,
                    'transparent': True,
                },
            ]

    class Chat_Settings(ConfigTabs):
        def __init__(self, parent):
            super().__init__(parent=parent)

            self.pages = {
                'Group': self.Page_Chat_Group(parent=self),
            }

        class Page_Chat_Group(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent
                self.conf_namespace = 'group'
                self.label_width = 175
                self.schema = [
                    {
                        'text': 'Output role',
                        'type': 'combo',
                        'table_name': 'roles',
                        'width': 90,
                        'tooltip': 'Set the primary output role for this member',
                        'default': 'user',
                    },
                    {
                        'text': 'Output placeholder',
                        'type': str,
                        'tooltip': 'A tag to use this member\'s output from other members system messages',
                        'default': '',
                    },
                    {
                        'text': 'Member description',
                        'type': str,
                        'num_lines': 4,
                        'label_position': 'top',
                        'stretch_x': True,
                        'tooltip': 'A description of the member that can be used by other members (Not implemented yet)',
                        'default': '',
                    },
                ]
