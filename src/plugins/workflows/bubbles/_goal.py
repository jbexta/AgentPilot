from plugins.workflows.bubbles import MessageBubble


class GoalBubble(MessageBubble):
    bubble_bg_color = '#1e2d22'
    bubble_text_color = '#6cd48c'

    def __init__(self, parent, message):
        super().__init__(parent=parent, message=message)