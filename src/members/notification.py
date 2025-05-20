from typing import Dict, Any

from src.gui.widgets import ConfigFields, ConfigJoined
from src.members.base import Member
from src.utils.helpers import set_module_type


@set_module_type(module_type='Members', settings='NotifSettings')
class Notif(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.workflow = kwargs.get('workflow')
        self.config: Dict[str, Any] = kwargs.get('config', {})
        self.receivable_function = None  #  self.receive

    async def run_member(self):
        from src.system import manager
        message = manager.blocks.format_string(
            self.config.get('message', ''),
            ref_workflow=self.workflow,
        )
        color = self.config.get('color', '#438BB9')
        self.main.show_notification_signal.emit(message, color)
        yield 'SYS', 'SKIP'  # todo not needed anymore


@set_module_type(module_type='Widgets')
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