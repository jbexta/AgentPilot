from typing import Any

from src.members import LlmMember
from src.utils.helpers import set_module_type


@set_module_type(module_type='Members', plugin='BLOCK', settings='prompt_block_settings')
class PromptBlock(LlmMember):
    default_role = 'block'
    default_avatar = ':/resources/icon-brain.png'
    default_name = 'Prompt'
    OUTPUT = str

    @property
    def INPUTS(self):
        return {
            'CONFIG': {
                'data': Any[str, list[str]],
            },
        }

    def __init__(self, **kwargs):
        super().__init__(model_config_key='prompt_model', **kwargs)

    def get_messages(self):  # todo
        return [{'role': 'user', 'content': self.get_content()}]