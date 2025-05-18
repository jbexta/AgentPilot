from src.gui.bubbles import MessageButton, MessageBubble
from src.utils.helpers import message_button


class CodeBubble(MessageBubble):
    def __init__(self, parent, message):
        super().__init__(
            parent=parent,
            message=message,
            readonly=False,
            autorun_button='btn_rerun',
            autorun_secs=5,
        )

    @message_button('btn_rerun')
    class RerunButton(MessageButton):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             icon_path=':/resources/icon-run-solid.png')

        def on_clicked(self):
            from src.utils.helpers import split_lang_and_code
            if self.msg_container.parent.workflow.responding:
                return
            # self.msg_container.btn_countdown.hide()

            bubble = self.msg_container.bubble
            member_id = self.msg_container.member_id
            lang, code = split_lang_and_code(bubble.text)
            code = bubble.toPlainText()

            self.msg_container.check_to_start_a_branch(
                role=bubble.role,
                new_message=f'```{lang}\n{code}\n```',
                member_id=member_id
            )

            from src.plugins.openinterpreter.src import interpreter
            oi_res = interpreter.computer.run(lang, code)
            output = next(r for r in oi_res if r['format'] == 'output').get('content', '')
            self.msg_container.parent.send_message(
                output,
                role='output',
                as_member_id=member_id,
                feed_back=True,
                clear_input=False
            )
