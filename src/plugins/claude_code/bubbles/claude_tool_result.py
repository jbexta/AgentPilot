from PySide6.QtCore import Qt

from plugins.workflows.bubbles import MessageBubble
from utils.helpers import set_module_type


@set_module_type(module_type='Bubbles')
class ClaudeToolResultBubble(MessageBubble):
    def __init__(self, parent, message):
        self._expanded = False
        super().__init__(parent=parent, message=message)
        self.viewport().setCursor(Qt.PointingHandCursor)

    def setMarkdownText(self, text, display_text=None):
        if not self._expanded:
            display_text = '*▶ Show result*'
        super().setMarkdownText(text, display_text=display_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._expanded = not self._expanded
            self.setMarkdownText(self.text)
            self.updateGeometry()
            return
        super().mousePressEvent(event)
