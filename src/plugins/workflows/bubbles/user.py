"""User Message Role GUI Module.

This module provides the UserBubble class, a specialized message role
for displaying user messages in the chat interface. User roles enable
message editing, resending, and user interaction controls within the
conversation view.

Key Features:
- User message display and editing capabilities
- Message resending and retry functionality
- Editable message content and formatting
- Interactive message controls and buttons
- Integration with workflow execution
- Branch management for message editing
- Message history and version control
- Theme and styling support

User roles provide an interactive interface for users to view, edit,
and manage their messages within conversations, enabling flexible
communication with AI systems.
"""  # unchecked

import qasync

from plugins.workflows.bubbles import MessageBubble, MessageButton
from utils.helpers import message_button


class UserBubble(MessageBubble):
    def __init__(self, parent, message):
        super().__init__(
            parent=parent,
            message=message,
            readonly=False,
        )

    @message_button('btn_resend')
    class ResendButton(MessageButton):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             icon_path=':/resources/icon-send.png')

        @qasync.asyncSlot()
        async def on_clicked(self):
            if self.msg_container.parent.workflow.responding:
                return
            msg_to_send = self.msg_container.bubble.text
            if msg_to_send == '':
                return

            self.msg_container.start_new_branch()

            # Finally send the message like normal
            run_workflow = self.msg_container.parent.workflow.config.get('config', {}).get('autorun', True)
            editing_member_id = self.msg_container.member_id
            msg_alt_turn = self.msg_container.message.alt_turn
            await self.msg_container.parent.workflow.send_message(msg_to_send, clear_input=False, as_member_id=editing_member_id, run_workflow=run_workflow, alt_turn=msg_alt_turn)
