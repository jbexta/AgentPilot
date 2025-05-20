
from src.members.base import Block
from src.utils.helpers import set_module_type


@set_module_type(module_type='Members', plugin='BLOCK', settings='TextBlockSettings')
class TextBlock(Block):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def receive(self):
        """The entry response method for the member."""
        content = self.get_content()
        yield self.default_role(), content
        self.workflow.save_message(self.default_role(), content, self.full_member_id())  # , logging_obj)


# @set_module_type(module_type='Members', plugin='BLOCK', settings='ModuleBlockSettings')
# class ModuleBlock(Block):
#     def __init__(self, **kwargs):
#         super().__init__(**kwargs)
#
#     async def receive(self):
#         """The entry response method for the member."""
#         raise NotImplementedError