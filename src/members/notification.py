from typing import Dict, Any

from PySide6.QtWidgets import QMessageBox

from src.gui.config import ConfigFields, ConfigJoined
from src.members.base import Member
from src.utils.helpers import display_message


class Notif(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.workflow = kwargs.get('workflow')
        self.config: Dict[str, Any] = kwargs.get('config', {})
        self.receivable_function = None  #  self.receive

    async def run_member(self):
        message = self.workflow.system.blocks.format_string(
            self.config.get('message', ''),
            ref_workflow=self.workflow,
        )
        color = self.config.get('color', '#438BB9')
        self.main.show_notification_signal.emit(message, color)
        yield 'SYS', 'SKIP'


class NotifSettings(ConfigJoined):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.widgets = [
            self.NotifFields(self),
        ]

    class NotifFields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.schema = [
                {
                    'text': 'Color',
                    'type': 'ColorPickerWidget',
                    'default': '#438BB9',
                },
                {
                    'text': 'Message',
                    'type': str,
                    'default': '',
                    'num_lines': 4,
                    'stretch_x': True,
                    'stretch_y': True,
                    'label_position': 'top',
                },
            ]