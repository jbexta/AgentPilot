"""Tool Approval Bubble Module.

Provides an interactive bubble for approving or rejecting Claude Code
tool usage requests. Displays tool name and parameters with Accept/Reject
buttons that resolve an asyncio.Future on the member instance.
"""

from plugins.workflows.bubbles import MessageBubble, MessageButton
from utils.helpers import message_button


def _format_tool_info(text):
    """Format tool approval text for display.

    Parameters
    ----------
    text : str
        Raw tool approval text in format 'Tool: <name>\n<details>'.

    Returns
    -------
    str
        Markdown-formatted display text.
    """
    lines = text.strip().split('\n', 1)
    header = lines[0] if lines else 'Tool Approval'
    details = lines[1].strip() if len(lines) > 1 else ''
    if details:
        return f"**{header}**\n\n```\n{details}\n```"
    return f"**{header}**"


class ToolApprovalBubble(MessageBubble):
    """Bubble for interactive tool usage approval.

    Displays tool information with Accept and Reject buttons.
    Resolves the member's ``_approval_future`` when user decides.
    """

    def __init__(self, parent, message):
        super().__init__(parent=parent, message=message)

    def setMarkdownText(self, text, display_text=None):
        display = _format_tool_info(text)
        super().setMarkdownText(text, display_text=display)

    def _resolve_future(self, approved):
        """Resolve the member's approval future.

        Parameters
        ----------
        approved : bool
            Whether the tool use was approved.
        """
        workflow = self.parent.parent.workflow
        member_id = self.member_id
        member = workflow.members.get(member_id)
        if member and hasattr(member, '_approval_future'):
            future = member._approval_future
            if future and not future.done():
                future.set_result(approved)
        # Clear from last_member_bubbles so next approval creates a new bubble
        msg_collection = self.parent.parent
        key = ('tool_approval', member_id)
        msg_collection.last_member_bubbles.pop(key, None)

    @message_button('btn_accept')
    class AcceptButton(MessageButton):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                icon_path=':/resources/icon-tick.svg',
            )
            self._always_visible = True
            self.show()

        def setVisible(self, visible):
            if getattr(self, '_always_visible', False):
                super().setVisible(True)
            else:
                super().setVisible(visible)

        def on_clicked(self):
            self.msg_container.bubble._resolve_future(True)
            self._always_visible = False
            self.hide()
            reject_btn = getattr(self.msg_container, 'btn_reject', None)
            if reject_btn:
                reject_btn._always_visible = False
                reject_btn.hide()

    @message_button('btn_reject')
    class RejectButton(MessageButton):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                icon_path=':/resources/icon-cross.png',
            )
            self._always_visible = True
            self.show()

        def setVisible(self, visible):
            if getattr(self, '_always_visible', False):
                super().setVisible(True)
            else:
                super().setVisible(visible)

        def on_clicked(self):
            self.msg_container.bubble._resolve_future(False)
            self._always_visible = False
            self.hide()
            accept_btn = getattr(self.msg_container, 'btn_accept', None)
            if accept_btn:
                accept_btn._always_visible = False
                accept_btn.hide()
