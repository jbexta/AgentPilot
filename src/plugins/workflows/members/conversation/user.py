from typing import Dict, Any
from plugins.workflows.members import Member
from utils.helpers import set_module_type


@set_module_type(module_type='Members', settings='user_settings')
class User(Member):
    default_role = 'user'
    default_avatar = ':/resources/icon-user.png'
    default_name = 'You'
    workflow_insert_mode = 'single'
    output_type = 'OUTPUT'
    conversational = True
    break_on_run = True
    allow_condition = False

    @property
    def INPUTS(self):
        return {
            'CONFIG': {
                'message_template': str,
            },
        }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.workflow = kwargs.get('workflow')
        self.config: Dict[str, Any] = kwargs.get('config', {})
        self.receivable_function = None

    # async def run(self):
    #     yield 'SYS', 'BREAK'