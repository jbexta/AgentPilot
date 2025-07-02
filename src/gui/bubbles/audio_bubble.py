import os
from utils.helpers import get_json_value, message_button
from gui.bubbles import MessageBubble, MessageButton


class AudioBubble(MessageBubble):
    def __init__(self, parent, message):
        super().__init__(
            parent=parent,
            message=message,
            readonly=True,
        )

    def setMarkdownText(self, text):
        filepath = get_json_value(text, 'filepath', 'Error parsing audio')
        filename = os.path.basename(filepath)
        super().setMarkdownText(filename)

    @message_button('btn_play')
    class PlayButton(MessageButton):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             icon_path=':/resources/icon-run-solid.png')

        def on_clicked(self):
            content = self.msg_container.message.content
            filepath = get_json_value(content, 'filepath', 'Error parsing audio')
            from utils.media import play_file
            play_file(filepath)