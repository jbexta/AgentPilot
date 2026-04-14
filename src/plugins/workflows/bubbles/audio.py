import os

from PySide6.QtWidgets import QWidget, QSizePolicy

from gui.media_previews.audio import AudioPreview
from gui.util import CVBoxLayout
from utils.helpers import get_json_value


class AudioBubble(QWidget):
    bubble_bg_color = '#00000000'
    bubble_text_color = '#ff949494'
    bubble_image_size = 25
    show_bubble = True

    def __init__(self, parent, message):
        super().__init__(parent=parent)
        self.parent = parent
        self.msg_id = message.id
        self.member_id = message.member_id
        self.role = message.role
        self.log = message.log
        self.text = ''
        self.collapsed = False
        self.filepath = None

        # Layout
        self.main_layout = CVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(5)

        # Styling
        # role_config = system.manager.roles.get(self.role, {})
        # bg_color = role_config.get('bubble_bg_color', '#252427')
        # text_color = role_config.get('bubble_text_color', '#999999')
        self.setStyleSheet(
            f"background-color: {self.bubble_bg_color}; "
            f"color: {self.bubble_text_color};"
        )

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Embedded preview
        self.audio_preview = AudioPreview(self)
        self.main_layout.addWidget(self.audio_preview)

        self.set_message(message)

    def set_message(self, message):
        """Initialize with message content."""
        self.msg_id = message.id
        self.member_id = message.member_id
        self.role = message.role
        self.log = message.log
        self.text = message.content

    def setMarkdownText(self, text):
        self.text = text
        filepath = get_json_value(text, 'filepath',
                                  'Error parsing audio')
        self.filepath = filepath
        if filepath and os.path.exists(filepath):
            self.audio_preview.set_filepath(filepath)
        else:
            self.audio_preview.filename_label.setText(
                os.path.basename(filepath) if filepath
                else 'Error parsing audio')

    def append_text(self, text):
        """Compatibility method for MessageBubble interface."""
        self.text += text
        self.setMarkdownText(self.text)

    def toPlainText(self):
        """Compatibility method for MessageBubble interface."""
        return self.text