from typing import Dict, Any

from src.members import Member
from src.utils.helpers import set_module_type


@set_module_type(module_type='Members', settings='notif_settings')
class Notif(Member):
    default_avatar = ':/resources/icon-notif.png'
    default_name = 'Notification'

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
