"""User Conversation Member Module.

This module provides the User member, representing human participants in
conversations and workflows. The User member enables human input, interaction
control, and serves as the primary interface for user-initiated communication
within multi-agent workflows.

Key Features:
- Human user representation in conversations
- Manual interaction control and input handling
- Integration with the workflow execution system
- Configuration management for user preferences
- Message flow control and workflow breaking
- Interactive workflow participation
- User session and state management

The User member enables human-in-the-loop workflows where users can
participate directly in conversations, provide input, and control
the flow of multi-agent interactions.
"""

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
