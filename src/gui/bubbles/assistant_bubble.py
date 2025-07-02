from gui.bubbles import MessageBubble


class AssistantBubble(MessageBubble):
    def __init__(self, parent, message):
        super().__init__(parent=parent, message=message)
