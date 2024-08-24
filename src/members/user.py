from abc import abstractmethod

from PySide6.QtGui import Qt

from src.gui.config import ConfigFields, ConfigPages, ConfigJsonTree, ConfigTabs
from src.gui.widgets import find_main_widget
from src.members.base import Member


class User(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.workflow = kwargs.get('workflow')
        self.config = kwargs.get('config', {})

    @abstractmethod
    async def run_member(self):
        """The entry response method for the member."""
        pass


class UserSettings(ConfigPages):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.main = find_main_widget(parent)
        self.member_type = 'user'
        self.member_id = None
        self.layout.addSpacing(10)

        self.pages = {
            'Info': self.Info_Settings(self),
            'Chat': self.Chat_Settings(self),
        }

    class Info_Settings(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.conf_namespace = 'info'
            self.alignment = Qt.AlignHCenter
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
                    'default': 'You',
                    'width': 400,
                    'text_size': 15,
                    'text_alignment': Qt.AlignCenter,
                    'label_position': None,
                    'transparent': True,
                    # 'fill_width': True,
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
                        'text': 'Output placeholder',
                        'type': str,
                        'tooltip': 'A tag to use this member\'s output from other members system messages',
                        'default': '',
                    },
                    {
                        'text': 'Member description',
                        'type': str,
                        'num_lines': 4,
                        'width': 320,
                        'tooltip': 'A description of the member that can be used by other members (Not implemented yet)',
                        'default': '',
                    }
                ]
