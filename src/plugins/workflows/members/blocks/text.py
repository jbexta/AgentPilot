"""Text Block Member Module.

This module provides the TextBlock member, a simple content block that outputs
static or templated text content within workflows. Text blocks serve as the
foundation for creating reusable text components, templates, and static content
that can be integrated into more complex workflows.

Key Features:
- Static text content output
- Template and placeholder support
- Integration with the block management system
- Lightweight and efficient text processing
- Support for dynamic content generation
- Workflow parameter integration
- Configurable text formatting and processing

Text blocks provide a simple but essential building block for creating
workflows that incorporate static content, templates, or formatted text output.
"""

from typing import Any

from plugins.workflows.members import Block
from utils.helpers import set_module_type


@set_module_type(module_type='Members', plugin='BLOCK', settings='text_settings')
class Text(Block):
    default_role = 'block'
    default_avatar = ':/resources/icon-blocks.png'
    default_name = 'Text'
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
        super().__init__(**kwargs)

    async def receive(self):
        """The entry response method for the member."""
        content = await self.get_content()
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