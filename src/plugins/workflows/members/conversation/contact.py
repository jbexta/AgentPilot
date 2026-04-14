from typing import Dict, Any
from plugins.workflows.members import Member
from utils.helpers import set_module_type


@set_module_type(module_type='Members', settings='contact_settings')
class Contact(Member):
    default_role = 'contact'
    default_avatar = ':/resources/icon-user.png'
    default_name = 'Contact'
    workflow_insert_mode = 'single'
    output_type = 'OUTPUT'
    conversational = True
    break_on_run = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.workflow = kwargs.get('workflow')
        self.config: Dict[str, Any] = kwargs.get('config', {})
        self.receivable_function = None

    # async def run(self):
    #     yield 'SYS', 'BREAK'