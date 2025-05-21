from typing import Dict, Any
from src.members.base import Member
from src.utils.helpers import set_module_type


@set_module_type(module_type='Members', settings='UserSettings')
class User(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.workflow = kwargs.get('workflow')
        self.config: Dict[str, Any] = kwargs.get('config', {})
        self.receivable_function = None

    async def run_member(self):
        yield 'SYS', 'BREAK'
