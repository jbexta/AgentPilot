from typing import Dict, Any

from plugins.workflows.members import Member
from utils.helpers import set_module_type


@set_module_type(module_type='Members', settings='notif_settings')
class Notif(Member):
    default_avatar = ':/resources/icon-notif.png'
    default_name = 'Notification'
    workflow_insert_mode = 'single'
    OUTPUT = None

    @property
    def INPUTS(self):
        return {
            'CONFIG': {
                'text': str,
            },
        }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receivable_function = None

    async def run(self):
        self.main.notification_manager.show_notification(
            message=self.config.get('text', ''), 
            icon=self.config.get('icon', 'Information'),
            title=self.config.get('title', None),
            color=self.config.get('color', '#438BB9'),
            duration=self.config.get('duration', 5000),
        )
        
        # # # Send notification
        # # self.main.tray.showMessage(
        # #     "Hello!",
        # #     "This is a PySide6 system notification.",
        # #     QSystemTrayIcon.Information,
        # #     5000  # duration in ms
        # # )
        # self.main.show_notification(
        #     self.config.get('text', ''), 
        #     title=self.config.get('title', ''), 
        #     color=color
        # )
        self.workflow.save_message('sys', f"Shown notification: {self.config.get('text', '')}", self.full_member_id())
        yield 'SYS', 'SKIP'  # todo not needed anymore