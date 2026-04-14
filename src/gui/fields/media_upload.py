import base64
import json
import mimetypes
import os

import qasync
from PySide6.QtCore import QPoint
from PySide6.QtGui import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QLabel, QMessageBox, QPushButton,
    QStackedWidget, QWidget, QLineEdit, QFileDialog, QSizePolicy,
)

from gui.util import IconButton, CHBoxLayout, CVBoxLayout, find_attribute
from utils import sql
from utils.helpers import (
    convert_model_json_to_obj, display_message, get_media_preview_class,
    set_module_type,
)


MEDIA_FILTERS = {
    'image': 'Image Files (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All Files (*)',
    'video': 'Video Files (*.mp4 *.avi *.mov *.mkv *.webm);;All Files (*)',
    'audio': 'Audio Files (*.mp3 *.wav *.flac *.ogg *.aac *.m4a);;All Files (*)',
    'any': 'All Files (*)',
}

SIZE_THRESHOLD = 1 * 1024 * 1024  # 1MB

# Maps media_type to compatible clip _TYPE values
COMPATIBLE_CLIP_TYPES = {
    'audio': {'audio', 'video'},
    'video': {'video'},
    'image': {'image'},
    'any': {'audio', 'video', 'image'},
}


class MediaSourcePopup(QWidget):
    """Popup for selecting a timeline or clip media source."""

    def __init__(self, parent, studio, media_type):
        super().__init__(parent)
        self.parent = parent
        self.studio = studio
        self.media_type = media_type

        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setFixedWidth(300)

        layout = CVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Source type combo
        self.source_combo = QComboBox(self)
        self.source_combo.addItems(['Timeline', 'Clip'])
        self.source_combo.currentIndexChanged.connect(
            self._on_source_changed
        )
        layout.addWidget(self.source_combo)

        # Stacked content
        self.stack = QStackedWidget(self)

        # Timeline page
        media_label = media_type if media_type != 'any' else 'media'
        self.timeline_page = QLabel(
            f'Use timeline {media_label} from clip position'
        )
        self.timeline_page.setWordWrap(True)
        self.stack.addWidget(self.timeline_page)

        # Clip page
        self.clip_page = QWidget()
        clip_layout = CVBoxLayout(self.clip_page)
        clip_layout.setContentsMargins(0, 0, 0, 0)
        clip_layout.setSpacing(4)

        self.clip_combo = QComboBox(self)
        self._populate_clips()
        clip_layout.addWidget(self.clip_combo)

        self.trim_checkbox = QCheckBox('Trim to timeline position', self)
        self.trim_checkbox.setChecked(True)
        clip_layout.addWidget(self.trim_checkbox)

        self.stack.addWidget(self.clip_page)

        layout.addWidget(self.stack)

        # Insert button
        self.insert_btn = QPushButton('Insert')
        self.insert_btn.clicked.connect(self._on_insert)
        layout.addWidget(self.insert_btn)

    def _populate_clips(self):
        """Fill clip combo with compatible timeline clips."""
        self.clip_combo.clear()
        allowed = COMPATIBLE_CLIP_TYPES.get(
            self.media_type, COMPATIBLE_CLIP_TYPES['any']
        )
        clips = self.studio.timeline.clips
        for clip_id, clip in clips.items():
            if clip.member_type not in allowed:
                continue
            name = clip.filename or clip.member_config.get(
                'name', f'Clip {clip_id}'
            )
            track_label = f'Track {clip.track_index + 1}'
            self.clip_combo.addItem(
                f'{name} ({track_label})', clip_id
            )

    def _on_source_changed(self, index):
        self.stack.setCurrentIndex(index)

    def _on_insert(self):
        """Build a source reference JSON and set it on the MediaUpload."""
        if self.source_combo.currentIndex() == 0:
            ref = {'source': 'timeline'}
        else:
            clip_id = self.clip_combo.currentData()
            if clip_id is None:
                return
            ref = {
                'source': 'clip',
                'clip_id': clip_id,
                'trim_to_position': self.trim_checkbox.isChecked(),
            }

        ref_str = json.dumps(ref)
        self.parent._local_path = None
        self.parent._clear_preview()
        self.parent.url_input.setText(ref_str)
        self.hide()
        if hasattr(self.parent.parent, 'update_config'):
            self.parent.parent.update_config()

    def showEvent(self, event):
        super().showEvent(event)
        self._populate_clips()
        btn = self.parent._source_button
        if btn:
            btm_right = btn.rect().bottomRight()
            global_pos = btn.mapToGlobal(btm_right)
            self.move(global_pos - QPoint(self.width(), 0))


@set_module_type('Fields')
class MediaUpload(QWidget):
    """A field widget that accepts a URL or local file for media input.

    Small files (< 1MB) are base64-encoded as data URIs. Larger files
    are uploaded to the provider's CDN asynchronously.

    When a studio timeline is detected in the parent hierarchy an extra
    button appears for inserting timeline/clip source references.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent)
        self.parent = parent
        width = kwargs.get('width', None)
        self.media_type = kwargs.get('media_type', 'any')
        placeholder = kwargs.get(
            'placeholder', 'Enter media URL or browse...'
        )

        self.layout = CHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)

        self.url_input = QLineEdit(self)
        self.url_input.setPlaceholderText(placeholder)
        self.url_input.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred
        )

        self.browse_button = IconButton(
            self, icon_path=':/resources/icon-folder.png'
        )
        self.browse_button.setMaximumWidth(60)
        self.browse_button.clicked.connect(self.browse_file)

        self._preview_widget = None
        self._preview_container = QWidget(self)
        self._preview_container.setFixedSize(32, 32)
        self._preview_container.setVisible(False)
        self._preview_layout = CHBoxLayout(self._preview_container)
        self._preview_layout.setContentsMargins(0, 0, 0, 0)

        self._local_path = None
        self._source_button = None
        self._source_popup = None

        self.layout.addWidget(self.url_input)
        self.layout.addWidget(self.browse_button)

        # Add studio source button if in a studio context
        studio, member_id = self._resolve_studio()
        if studio is not None:
            self._source_button = IconButton(
                self, icon_path=':/resources/icon-link.png'
            )
            self._source_button.setMaximumWidth(60)
            self._source_button.clicked.connect(self._toggle_source_popup)
            self._source_popup = MediaSourcePopup(
                self, studio, self.media_type
            )
            self.layout.addWidget(self._source_button)

        self.layout.addWidget(self._preview_container)

        if width:
            self.setFixedWidth(width)
            button_width = self.browse_button.maximumWidth()
            spacing = self.layout.spacing()
            input_width = width - button_width - spacing - 10
            self.url_input.setFixedWidth(max(input_width, 100))

        self.url_input.textChanged.connect(parent.update_config)

    def _resolve_studio(self):
        """Find the studio and target clip member_id from parent hierarchy.

        Returns
        -------
        tuple
            (studio_widget, member_id) or (None, None) if not in a studio.
        """
        member_id = find_attribute(self, 'member_id')
        widget = self.parent
        while widget is not None:
            if (hasattr(widget, 'timeline')
                    and hasattr(widget.timeline, 'clips')):
                return widget, member_id
            widget = getattr(widget, 'parent', None)
        return None, None

    def _toggle_source_popup(self):
        """Show or hide the media source popup."""
        if self._source_popup.isVisible():
            self._source_popup.hide()
        else:
            self._source_popup.show()

    def get_value(self):
        """Returns the current value as a JSON dict or plain URL string.

        When a local_path is stored the value is serialised as
        ``{"url": "<cdn_url>", "local_path": "/path/to/file"}``.
        Source references (timeline/clip) are returned as-is.
        Otherwise a plain URL string is returned.
        """
        url = self.url_input.text()
        # Check for source reference
        try:
            obj = json.loads(url)
            if isinstance(obj, dict) and 'source' in obj:
                return url
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        if self._local_path:
            return json.dumps({
                'url': url,
                'local_path': self._local_path,
            })
        return url

    def set_value(self, value):
        """Sets the URL or data URI.

        Accepts either a plain string URL, a JSON-encoded dict with
        ``url`` and ``local_path`` keys, or a source reference dict
        with a ``source`` key.
        """
        if not value:
            return
        value = str(value)
        try:
            obj = json.loads(value)
            if isinstance(obj, dict):
                # Source reference — just display the JSON text
                if 'source' in obj:
                    self._local_path = None
                    self._clear_preview()
                    self.url_input.setText(value)
                    return
                self.url_input.setText(obj.get('url', ''))
                local_path = obj.get('local_path', '')
                if local_path and os.path.isfile(local_path):
                    self._local_path = local_path
                    self._show_preview(local_path)
                return
        except (json.JSONDecodeError, TypeError):
            pass
        self.url_input.setText(value)

    def clear_value(self):
        """Clears the input field, preview, and local path."""
        self.url_input.clear()
        self._local_path = None
        self._clear_preview()

    def browse_file(self):
        """Opens a file dialog and processes the selected file."""
        file_filter = MEDIA_FILTERS.get(
            self.media_type, MEDIA_FILTERS['any'])
        current = self.url_input.text()
        start_dir = ''
        if current and not current.startswith(('http', 'data:')):
            start_dir = current

        path, _ = QFileDialog.getOpenFileName(
            self, 'Select Media File', start_dir, file_filter
        )
        if not path:
            return

        self._local_path = path
        self._show_preview(path)
        self._start_upload(path)

    def _show_preview(self, filepath):
        """Display an inline preview thumbnail for *filepath*.

        Detects the media type from the file extension and instantiates
        the appropriate preview widget (ImagePreview, VideoPreview, or
        AudioPreview).
        """
        self._clear_preview()
        ext = os.path.splitext(filepath)[1].lower()

        preview_class = get_media_preview_class(ext=ext)
        if preview_class is None:
            return
        preview = preview_class(parent=self._preview_container)
        preview.set_filepath(filepath)

        preview.setFixedSize(32, 32)
        self._preview_layout.addWidget(preview)
        self._preview_widget = preview
        self._preview_container.setVisible(True)

    def _clear_preview(self):
        """Remove the current preview widget, if any."""
        if self._preview_widget is not None:
            if hasattr(self._preview_widget, 'cleanup'):
                self._preview_widget.cleanup()
            self._preview_widget.setParent(None)
            self._preview_widget.deleteLater()
            self._preview_widget = None
        self._preview_container.setVisible(False)

    @qasync.asyncSlot()
    async def _start_upload(self, file_path):
        """Async entry point for uploading a large file."""
        await self._upload_file(file_path)

    def _set_base64_value(self, file_path):
        """Base64-encode a small file and set as data URI."""
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = 'application/octet-stream'
        with open(file_path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('ascii')
        self.url_input.setText(f'data:{mime_type};base64,{data}')

    async def _upload_file(self, file_path):
        """Upload a large file to the provider's CDN."""
        from gui import system

        self.url_input.setPlaceholderText('Uploading...')
        self.browse_button.setEnabled(False)
        try:
            provider_name = self._resolve_provider()
            provider_instance = system.manager.providers.get(provider_name)

            if not provider_instance:
                raise Exception("Provider not found")
            url = await provider_instance.upload_file(file_path)
            self.url_input.setText(url)

        except Exception as e:
            display_message(
                icon=QMessageBox.Critical,
                title="Error uploading media",
                message=f"An error occurred while uploading media: {e}",
            )
        finally:
            self.url_input.setPlaceholderText(
                'Enter media URL or browse...'
            )
            self.browse_button.setEnabled(True)

    def _resolve_provider(self):
        """Walk parent hierarchy to find provider name

        Returns
        -------
        string
            provider_instance or None if unresolved.
        """
        from gui.fields.model import ModelComboBox

        widget = self.parent
        while widget is not None:
            if hasattr(widget, 'provider_name'):
                return widget.provider_name
            # Check children for ModelComboBox
            for child in getattr(widget, 'children', lambda: [])():
                if isinstance(child, ModelComboBox):
                    return self._resolve_from_model_combo(child)

            # Check if this widget itself has a model combo
            if isinstance(widget, ModelComboBox):
                return self._resolve_from_model_combo(widget)

            # Check for Tab_Kind_Models (ConfigDBTree with models)
            cls_name = type(widget).__name__
            if cls_name == 'Tab_Kind_Models':
                return self._resolve_from_tree(widget)

            widget = getattr(widget, 'parent', None)

        return None

    def _resolve_from_model_combo(self, combo):
        """Extract provider and api_key from a ModelComboBox."""
        model_obj = combo.get_value()
        if not model_obj or not model_obj.get('_model_name'):
            return None

        provider_name = model_obj.get('provider', '')
        return provider_name

    def _resolve_from_tree(self, tree_widget):
        """Extract provider and api_key from a Tab_Kind_Models tree."""
        item_id = tree_widget.get_selected_item_id()
        if not item_id:
            return None

        return sql.get_scalar("""
            SELECT provider_plugin
            FROM models
            WHERE id = ?
        """, (item_id,))