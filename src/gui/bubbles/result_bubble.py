
from src.utils.helpers import get_json_value
from src.gui.bubbles import MessageBubble


class ResultBubble(MessageBubble):
    def __init__(self, parent, message):
        super().__init__(
            parent=parent,
            message=message,
        )

    def setMarkdownText(self, text):
        display_text = get_json_value(text, 'output', 'Error parsing result')
        super().setMarkdownText(text, display_text=display_text)
