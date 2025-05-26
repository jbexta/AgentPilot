
from src.members.base import LlmMember
from src.utils.helpers import set_module_type


@set_module_type(module_type='Members', plugin='BLOCK', settings='prompt_block_settings')
class PromptBlock(LlmMember):
    default_role = 'block'

    def __init__(self, **kwargs):
        super().__init__(model_config_key='prompt_model', **kwargs)

    def get_content(self, run_sub_blocks=True):  # todo dupe code 777
        # We have to redefine this here because we inherit from LlmMember
        from src.system import manager
        content = self.config.get('data', '')

        if run_sub_blocks:
            block_type = self.config.get('_PLUGIN', 'Text')
            nestable_block_types = ['Text', 'Prompt']
            if block_type in nestable_block_types:
                content = manager.blocks.format_string(content, ref_workflow=self.workflow)

        return content

    def get_messages(self):  # todo
        return [{'role': 'user', 'content': self.get_content()}]