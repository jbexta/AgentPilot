from typing import Any

from plugins.workflows.members import LlmMember
from utils.helpers import set_module_type


@set_module_type(module_type='Members', plugin='BLOCK', settings='prompt_settings')
class Prompt(LlmMember):
    default_role = 'block'
    default_avatar = ':/resources/icon-brain.png'
    default_name = 'Prompt'
    workflow_insert_mode = 'list'
    OUTPUT = str

    @property
    def INPUTS(self):
        return {
            'CONFIG': {
                'data': str,
            },
        }

    def __init__(self, **kwargs):
        super().__init__(model_config_key='prompt_model', **kwargs)

    async def get_messages(self):  # todo
        return [{'role': 'user', 'content': await self.get_content()}]