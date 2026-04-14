from typing import Dict, Any

from plugins.workflows.members import Member
from utils.helpers import set_module_type


@set_module_type(module_type='Members')  # , settings='notif_settings')
class SetVariable(Member):
    default_avatar = ':/resources/icon-notif.png'
    default_name = 'Set Variable'
    workflow_insert_mode = 'single'
    OUTPUT = None

    @property
    def INPUTS(self):
        return {
            'CONFIG': {
                'scope': str,  # 'global', 'workflow'
                'ephemeral': bool,
                'variable': str,
                'value': str,
            },
        }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receivable_function = None  #  self.receive

    async def run(self):
        pass
        yield 'SYS', 'SKIP'  # todo not needed anymore