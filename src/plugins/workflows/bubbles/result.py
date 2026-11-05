from gui import system as gui_system
from utils.helpers import get_json_value, blend_hex_colors
from plugins.workflows.bubbles import MessageBubble


class ResultBubble(MessageBubble):
    bubble_text_color = '#ff818365'

    def __init__(self, parent, message):
        text_color = gui_system.manager.config.get('display.text_color', '#ffcacdd5')
        super().__init__(
            parent=parent,
            message=message,
            bubble_text_color=blend_hex_colors(text_color, self.bubble_text_color, 0.5),
        )

    def set_message(self, message):
        super().set_message(message)
        self.enable_markdown = False

    def setMarkdownText(self, text):
        display_text = get_json_value(text, 'output', 'Error parsing result')
        super().setMarkdownText(text, display_text=display_text)