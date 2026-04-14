import qasync

from gui import system as gui_system
from plugins.workflows.bubbles import MessageBubble, MessageButton
from utils.helpers import message_button


class UserBubble(MessageBubble):
    bubble_text_color = '#ffd1d1d1'
    bubble_bg_opacity = 0.15

    def __init__(self, parent, message):
        text_color = gui_system.manager.config.get(
            'display.text_color', '#ffcacdd5')
        super().__init__(
            parent=parent,
            message=message,
            readonly=False,
            bubble_bg_color=text_color,
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