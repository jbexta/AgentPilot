from typing import Any

from src.members import Block
from src.utils.helpers import set_module_type


@set_module_type(module_type='Members', plugin='BLOCK', settings='text_block_settings')
class TextBlock(Block):
    default_role = 'block'
    default_avatar = ':/resources/icon-blocks.png'
    default_name = 'Text'
    OUTPUT = str

    @property
    def INPUTS(self):
        return {
            'CONFIG': {
                'data': Any[str, list[str]],
            },
        }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def receive(self):
        """The entry response method for the member."""
        content = self.get_content()
        yield self.default_role, content
        self.workflow.save_message(self.default_role, content, self.full_member_id())  # , logging_obj)


# @set_module_type(module_type='Members', plugin='BLOCK', settings='ModuleBlockSettings')
# class ModuleBlock(Block):
#     def __init__(self, **kwargs):
#         super().__init__(**kwargs)
#
#     async def receive(self):
#         """The entry response method for the member."""
#         raise NotImplementedError