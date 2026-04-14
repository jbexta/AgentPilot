from gui import system as gui_system
from plugins.workflows.bubbles import MessageBubble


class AssistantBubble(MessageBubble):
    bubble_text_color = '#ffb2bbcf'
    bubble_bg_opacity = 0.07

    def __init__(self, parent, message):
        text_color = gui_system.manager.config.get(
            'display.text_color', '#ffcacdd5')
        super().__init__(
            parent=parent,
            message=message,
            bubble_bg_color=text_color,
        )