from abc import abstractmethod

from PySide6.QtGui import Qt

from src.gui.config import ConfigFields, ConfigPages
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
    def __init__(self, parent):  # , is_context_member_agent=False):
        super().__init__(parent=parent)
        # self.parent = parent
        self.main = find_main_widget(parent)
        self.member_type = 'user'
        # self.is_context_member_agent = is_context_member_agent
        self.ref_id = None
        self.layout.addSpacing(10)

        self.pages = {
            'Info': self.Info_Settings(self),
        }
        self.build_schema()

    class Info_Settings(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.namespace = 'info'
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
                    'fill_width': True,
                },
            ]
            self.build_schema()
