from src.gui.bubbles import MessageBubble, MessageButton
from src.utils.helpers import message_button


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

        def on_clicked(self):
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
            self.msg_container.parent.send_message(msg_to_send, clear_input=False, as_member_id=editing_member_id, run_workflow=run_workflow, alt_turn=msg_alt_turn)
