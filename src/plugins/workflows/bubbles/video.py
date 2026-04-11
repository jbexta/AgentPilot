"""Video Message Role GUI Module.

This module provides the VideoBubble class, a specialized message role
for displaying videos in the chat interface. Video roles handle video
loading, display, playback controls, and various video formats within
conversations.

Key Features:
- Video display and rendering capabilities
- Support for multiple video formats and sources
- Playback controls (play, pause, seek, volume)
- Video loading from files and URLs
- Error handling for invalid or corrupted videos
- Integration with the message role framework
- Dynamic video sizing and scaling
- Video metadata and path handling
- Automatic polling for queued video generation requests

Video roles provide a rich multimedia interface for viewing videos
within conversations, enabling visual content sharing and
media communication with AI systems.
"""

from PySide6.QtWidgets import QWidget, QLabel, QSizePolicy

from gui.media_previews.video import VideoPreview
from gui.util import CVBoxLayout
from utils.helpers import get_json_value
from utils import sql
from gui import system


class VideoBubble(QWidget):
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
        # self.poll_future = None
        # self.request_id = None
        self.model_name = None
        self.filepath = None
        self.status_label = None

        # self.destroyed.connect(self.cleanup)

        # Setup layout
        self.main_layout = CVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(5)

        # Apply styling
        role_config = system.manager.roles.get(self.role, {})
        bg_color = role_config.get('bubble_bg_color', '#252427')
        text_color = role_config.get('bubble_text_color', '#999999')
        self.setStyleSheet(
            f"background-color: {bg_color}; color: {text_color};")

        # Set size policy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Embedded preview
        self.video_preview = None

        # Set message content
        self.set_message(message)

    def set_message(self, message):
        """Initialize the video player with message content."""
        self.text = message.content

        filepath = get_json_value(self.text, 'filepath')
        url = get_json_value(self.text, 'url')
        request_id = get_json_value(self.text, 'request_id')
        model_name = get_json_value(self.text, 'model_name')
        # status = get_json_value(self.text, 'status')

        self.filepath = filepath
        self.request_id = request_id
        self.model_name = model_name

        # if request_id and status != 'completed':
        #     if not filepath or not os.path.exists(filepath):
        #         self.show_polling_status()
        #         self.start_polling()
        #         return

        if url or filepath:
            try:
                self._setup_preview(filepath, url)
            except Exception as e:
                print(f"Error loading video: {e}")
                error_label = QLabel(
                    f"Error loading video: {filepath or url}")
                self.main_layout.addWidget(error_label)
        else:
            error_label = QLabel(
                "No valid video path or URL provided")
            self.main_layout.addWidget(error_label)

    def _setup_preview(self, filepath, url):
        """Create and configure a VideoPreview."""
        self.video_preview = VideoPreview(self)
        self.main_layout.addWidget(self.video_preview)
        if filepath:
            self.video_preview.set_filepath(filepath)
        elif url:
            self.video_preview.set_url(url)

    def setMarkdownText(self, text):
        """Compatibility method for MessageBubble interface."""
        self.text = text
        filepath = get_json_value(text, 'filepath')
        url = get_json_value(text, 'url')
        if (filepath or url) and self.video_preview \
                and self.video_preview.media_player:
            if filepath:
                from PySide6.QtCore import QUrl
                self.video_preview.media_player.setSource(
                    QUrl.fromLocalFile(filepath))
            elif url:
                from PySide6.QtCore import QUrl
                self.video_preview.media_player.setSource(QUrl(url))

    def append_text(self, text):
        """Compatibility method for MessageBubble interface."""
        pass

    def toPlainText(self):
        """Compatibility method for MessageBubble interface."""
        return self.text

    # def show_polling_status(self):
    #     """Show a status label while polling."""
    #     self.status_label = QLabel("Generating video...")
    #     self.status_label.setAlignment(Qt.AlignCenter)
    #     self.status_label.setStyleSheet(
    #         "font-size: 14px; padding: 20px;")
    #     self.main_layout.addWidget(self.status_label)

    # def start_polling(self):
    #     """Start polling for video completion."""
    #     self.poll_timer = QTimer(self)
    #     self.poll_timer.timeout.connect(self.poll_status)
    #     self.poll_timer.start(3000)
    #     self.poll_status()

    # def poll_status(self):
    #     """Check if video generation is complete."""
    #     self.poll_future = asyncio.ensure_future(
    #         self._async_poll_status())

    # async def _async_poll_status(self):
    #     """Async polling implementation."""
    #     import fal_client

    #     try:
    #         api_key = os.environ.get('FAL_API_KEY')
    #         if api_key:
    #             os.environ['FAL_KEY'] = api_key

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
    #     """Download completed video and display it."""
    #     import fal_client
    #     import requests

    #     self.status_label.setText("Downloading...")

    #     response = await fal_client.result_async(
    #         self.model_name, self.request_id)

    #     media_url = None
    #     if 'video' in response:
    #         media_url = response['video'].get('url')
    #     elif 'url' in response:
    #         media_url = response['url']

    #     if not media_url:
    #         self.status_label.setText(
    #             "Error: No video URL in response")
    #         return

    #     filename = os.path.basename(media_url)
    #     app_path = get_application_path()
    #     base_dir = os.path.join(app_path, self.role)
    #     filepath = os.path.join(base_dir, filename)

    #     with requests.get(media_url, stream=True) as r:
    #         r.raise_for_status()
    #         os.makedirs(base_dir, exist_ok=True)
    #         with open(filepath, 'wb') as f:
    #             for chunk in r.iter_content(chunk_size=8192):
    #                 if chunk:
    #                     f.write(chunk)
    #         self.filepath = filepath

    #     msg_json = {
    #         'filepath': filepath,
    #     }
    #     sql.execute(
    #         "UPDATE contexts_messages SET msg = ? WHERE id = ?",
    #         (json.dumps(msg_json), self.msg_id)
    #     )

    #     if self.status_label:
    #         self.status_label.deleteLater()
    #         self.status_label = None
    #     self._setup_preview(self.filepath, None)

    # def cleanup(self):
    #     """Clean up resources."""
    #     if self.poll_timer:
    #         self.poll_timer.stop()
    #     if self.poll_future and not self.poll_future.done():
    #         self.poll_future.cancel()
    #     if self.video_preview:
    #         self.video_preview.cleanup()
