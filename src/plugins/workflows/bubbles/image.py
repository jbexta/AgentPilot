"""Image Message Role GUI Module.

This module provides the ImageBubble class, a specialized message role
for displaying images in the chat interface. Image roles handle image
loading, display, zoom functionality, and various image formats within
conversations.

Key Features:
- Image display and rendering capabilities
- Support for multiple image formats and sources
- Zoom and pan functionality for image viewing
- Image loading from files and URLs
- Error handling for invalid or corrupted images
- Integration with the message role framework
- Dynamic image sizing and scaling
- Image metadata and path handling
- Automatic polling for queued image generation requests

Image roles provide a rich visual interface for viewing images
within conversations, enabling multimedia communication and
visual content sharing with AI systems.
"""

import asyncio
import json
import os

from PySide6.QtCore import QTimer
from PySide6.QtGui import Qt
from PySide6.QtWidgets import QWidget, QLabel, QSizePolicy

from gui.media_previews.image import ImagePreview
from gui.util import CVBoxLayout
from utils.filesystem import get_application_path
from utils.helpers import get_json_value
from utils import sql
from gui import system


class ImageBubble(QWidget):
    def __init__(self, parent, message):
        super().__init__(parent=parent)
        self.parent = parent
        self.msg_id = message.id
        self.member_id = message.member_id
        self.role = message.role
        self.log = message.log
        self.text = ''
        self.collapsed = False

        # # Polling components
        # self.poll_timer = None
        # self.request_id = None
        self.model_name = None
        self.filepath = None

        # Layout
        self.main_layout = CVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(5)

        # Styling
        role_config = system.manager.roles.get(self.role, {})
        bg_color = role_config.get('bubble_bg_color', '#252427')
        text_color = role_config.get('bubble_text_color', '#999999')
        self.setStyleSheet(
            f"background-color: {bg_color}; color: {text_color};")

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Embedded preview
        self.image_preview = ImagePreview(self)
        self.main_layout.addWidget(self.image_preview)
        self.image_preview.hide()

        # Status label (shown while polling)
        self.status_label = QLabel(self)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.status_label)
        self.status_label.hide()

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

        filepath = get_json_value(text, 'filepath')
        url = get_json_value(text, 'url')
        request_id = get_json_value(text, 'request_id')
        model_name = get_json_value(text, 'model_name')
        status = get_json_value(text, 'status')

        self.filepath = filepath
        self.request_id = request_id
        self.model_name = model_name

        if request_id and status != 'completed':
            if not filepath or not os.path.exists(filepath):
                self.status_label.setText("Generating image...")
                self.status_label.show()
                self.image_preview.hide()
                # self.start_polling()
                return

        if not url and filepath:
            try:
                self.image_preview.set_filepath(filepath)
                if self.image_preview.image is None \
                        or self.image_preview.image.isNull():
                    raise Exception("Invalid image")
                self.image_preview.show()
                self.status_label.hide()
            except Exception as e:
                print(f"Error reading image file: {e}")
                self.status_label.setText(
                    f"Error loading image: {filepath}")
                self.status_label.show()
                self.image_preview.hide()
        else:
            self.status_label.setText(
                "No valid image path or URL provided")
            self.status_label.show()
            self.image_preview.hide()

    def append_text(self, text):
        """Compatibility method for MessageBubble interface."""
        self.text += text
        self.setMarkdownText(self.text)

    def toPlainText(self):
        """Compatibility method for MessageBubble interface."""
        return self.text

    # def start_polling(self):
    #     """Start polling for image completion."""
    #     self.poll_timer = QTimer(self)
    #     self.poll_timer.timeout.connect(self.poll_status)
    #     self.poll_timer.start(3000)
    #     self.poll_status()

    # def poll_status(self):
    #     """Check if image generation is complete."""
    #     asyncio.ensure_future(self._async_poll_status())

    # async def _async_poll_status(self):
    #     """Async polling implementation."""
    #     import fal_client

    #     try:
    #         api_key = os.environ.get('FAL_API_KEY')
    #         if api_key:
    #             os.environ['FAL_API_KEY'] = api_key

    #         status = await fal_client.status_async(
    #             self.model_name, self.request_id)

    #         if isinstance(status, fal_client.Queued):
    #             self.status_label.setText(
    #                 f"Queued (position: {status.position})")
    #         elif isinstance(status, fal_client.InProgress):
    #             self.status_label.setText("Generating...")
    #         elif isinstance(status, fal_client.Completed):
    #             self.poll_timer.stop()
    #             await self.download_and_display()

    #     except Exception as e:
    #         print(f"Polling error: {e}")
    #         self.status_label.setText(f"Error: {e}")

    # async def download_and_display(self):
    #     """Download completed image and display it."""
    #     import fal_client
    #     import requests

    #     self.status_label.setText("Downloading...")

    #     response = await fal_client.result_async(
    #         self.model_name, self.request_id)

    #     media_url = None
    #     if 'images' in response and response['images']:
    #         media_url = response['images'][0].get('url')
    #     elif 'image' in response:
    #         media_url = response['image'].get('url')
    #     elif 'url' in response:
    #         media_url = response['url']

    #     if not media_url:
    #         self.status_label.setText("Error: No image URL in response")
    #         return

    #     media_response = requests.get(media_url, stream=True)
    #     media_response.raise_for_status()

    #     filename = os.path.basename(media_url)
    #     app_path = get_application_path()
    #     base_dir = os.path.join(app_path, self.role)
    #     filepath = os.path.join(base_dir, filename)

    #     with open(filepath, 'wb') as f:
    #         for chunk in media_response.iter_content(chunk_size=8192):
    #             if chunk:
    #                 f.write(chunk)

    #     self.filepath = filepath
    #     msg_json = {
    #         'filepath': filepath,
    #     }
    #     sql.execute(
    #         "UPDATE contexts_messages SET msg = ? WHERE id = ?",
    #         (json.dumps(msg_json), self.msg_id)
    #     )

    #     self.image_preview.set_filepath(self.filepath)
    #     if self.image_preview.image \
    #             and not self.image_preview.image.isNull():
    #         self.image_preview.show()
    #         self.status_label.hide()
    #     else:
    #         self.status_label.setText("Error loading downloaded image")

    # def cleanup(self):
    #     """Clean up resources."""
    #     if self.poll_timer:
    #         self.poll_timer.stop()
