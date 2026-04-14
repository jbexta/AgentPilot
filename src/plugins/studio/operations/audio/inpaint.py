import asyncio
import json
import os

import aiohttp
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import (
    QDialog, QGraphicsItem, QGraphicsItemGroup,
    QGraphicsLineItem, QGraphicsRectItem, QHBoxLayout,
    QLabel, QPushButton, QVBoxLayout, QWidget,
)

from gui import system
from gui.style import ACCENT_COLOR_2
from gui.widgets.config_fields import ConfigFields
from plugins.studio.operations.base import BaseOperation
from utils.helpers import convert_model_json_to_obj


# ---------------------------------------------------------------------------
# Timing parameter mapping
# ---------------------------------------------------------------------------

TIMING_PARAM_MAP = {
    ('sonauto', 'v2-inpaint'): (
        'section_start', 'section_end', float,
    ),
    ('fal', 'fal-ai/ace-step'): (
        'start_time', 'end_time', float,
    ),
    ('fal', 'fal-ai/stable-audio'): (
        'mask_start', 'mask_end', int,
    ),
    ('wavespeed', 'ace-step'): (
        'start_time', 'end_time', float,
    ),
}


def get_timing_params(provider, model_name):
    """Return (start_key, end_key, cast_fn) for a provider/model pair.

    Tries exact match first, then partial match on model_name.
    Falls back to ``('start_time', 'end_time', float)``.
    """
    key = (provider, model_name)
    if key in TIMING_PARAM_MAP:
        return TIMING_PARAM_MAP[key]

    for (p, pattern), value in TIMING_PARAM_MAP.items():
        if p == provider and pattern in model_name:
            return value

    return ('start_time', 'end_time', float)


class Inpaint(BaseOperation):
    """Replace a section of audio with AI-generated content."""

    display_name = 'Inpaint'
    description = 'Replace a section of audio with AI-generated content'
    icon_path = ':/resources/icon-audio.png'

    class InpaintFlagItem(QGraphicsItemGroup):
        """Draggable inpaint region flag bound to a clip."""

        def __init__(self, height, clip, is_start=True, parent=None):
            super().__init__(parent)
            self._is_start = is_start
            self._dragging = False
            self._drag_offset = 0
            self.timeline_view = None
            self.frame = 0
            self.clip = clip
            self.partner = None

            color = QColor(ACCENT_COLOR_2)
            pen = QPen(color, 1)
            pen.setCosmetic(True)

            self._line = QGraphicsLineItem(0, 0, 0, height)
            self._line.setPen(pen)
            self.addToGroup(self._line)

            if is_start:
                self._handle = QGraphicsRectItem(-10, 0, 10, 10)
            else:
                self._handle = QGraphicsRectItem(0, 0, 10, 10)
            self._handle.setBrush(QBrush(color))
            self._handle.setPen(QPen(Qt.NoPen))
            self.addToGroup(self._handle)

            self.setZValue(99)
            self.setFlag(QGraphicsItem.ItemIsMovable, False)

        def update_height(self, h):
            """Resize the vertical line when tracks change."""
            self._line.setLine(0, 0, 0, h)

        def get_seconds(self):
            """Convert flag frame position to seconds."""
            fps = self.timeline_view.studio.project_fps
            source_frame = (
                (self.frame - self.clip.start_frame)
                + self.clip.in_frame
            )
            return source_frame / fps

        # -- drag handling --

        def mousePressEvent(self, event):
            handle_rect = self._handle.mapToScene(
                self._handle.boundingRect()
            ).boundingRect()
            if handle_rect.contains(event.scenePos()):
                self._dragging = True
                self._drag_offset = (
                    event.scenePos().x() - self.pos().x()
                )
                event.accept()
            else:
                event.ignore()

        def mouseMoveEvent(self, event):
            if not self._dragging:
                event.ignore()
                return
            new_x = event.scenePos().x() - self._drag_offset
            if new_x < 0:
                new_x = 0
            self.setPos(new_x, 0)
            event.accept()

        def mouseReleaseEvent(self, event):
            if not self._dragging:
                event.ignore()
                return
            self._dragging = False

            if not self.timeline_view:
                event.accept()
                return

            upf = self.timeline_view.units_per_frame
            frame = round(self.pos().x() / upf)

            # Clamp to clip bounds
            clip_start = self.clip.start_frame
            clip_end = clip_start + self.clip.frame_count
            frame = max(clip_start, min(frame, clip_end))

            # Enforce start < end via partner
            if self.partner is not None:
                if self._is_start and frame >= self.partner.frame:
                    frame = self.partner.frame - 1
                elif (
                    not self._is_start
                    and frame <= self.partner.frame
                ):
                    frame = self.partner.frame + 1

            # Re-clamp after partner enforcement
            frame = max(clip_start, min(frame, clip_end))

            self.frame = frame
            self.setPos(frame * upf, 0)
            event.accept()

    def run(self):
        """Show a non-modal inpaint dialog for each selected clip."""
        for clip in self.clips_to_modify:
            if not clip.filepath or not os.path.exists(clip.filepath):
                continue
            dialog = self.InpaintDialog(self.studio, clip)
            dialog.show()

    # -------------------------------------------------------------------
    # Dialog
    # -------------------------------------------------------------------

    class InpaintDialog(QDialog):
        """Non-modal dialog for audio inpainting."""

        def __init__(self, studio, clip):
            super().__init__(studio)
            self.setWindowFlags(
                Qt.Window
                | Qt.WindowTitleHint
                | Qt.WindowSystemMenuHint
                | Qt.WindowCloseButtonHint
                | Qt.WindowStaysOnTopHint
            )
            self.studio = studio
            self.clip = clip
            self._thread = None

            self.setWindowTitle("Inpaint Audio")
            self.resize(450, 350)
            self.setWindowModality(Qt.NonModal)
            self.setAttribute(Qt.WA_DeleteOnClose)

            layout = QVBoxLayout(self)

            # Model selector with per-model params
            self.config_fields = ConfigFields(
                self,
                schema=[{
                    'text': 'Model',
                    'key': 'model',
                    'type': 'model',
                    'model_kind': 'AUDIO',
                    'width': 350,
                    'stretch_y': True,
                }],
            )
            self.config_fields.build_schema()
            self.config_fields.load()
            layout.addWidget(self.config_fields)

            # Region labels row
            region_row = QWidget()
            region_layout = QHBoxLayout(region_row)
            region_layout.setContentsMargins(0, 0, 0, 0)
            self.start_label = QLabel("Start: 0.0s")
            self.end_label = QLabel("End: 0.0s")
            region_layout.addWidget(self.start_label)
            region_layout.addStretch()
            region_layout.addWidget(self.end_label)
            layout.addWidget(region_row)

            # Status label
            self.status_label = QLabel("")
            layout.addWidget(self.status_label)

            # Buttons
            button_box = QWidget()
            button_layout = QHBoxLayout(button_box)
            button_layout.setContentsMargins(0, 0, 0, 0)
            self.btn_inpaint = QPushButton("Inpaint")
            self.btn_inpaint.clicked.connect(self.start_inpaint)
            self.btn_cancel = QPushButton("Cancel")
            self.btn_cancel.clicked.connect(self.close)
            button_layout.addStretch()
            button_layout.addWidget(self.btn_cancel)
            button_layout.addWidget(self.btn_inpaint)
            layout.addWidget(button_box)

            # Create flags on the timeline
            self._create_flags()

            # Timer to poll flag positions and update labels
            self._poll_timer = QTimer(self)
            self._poll_timer.timeout.connect(self._update_region_labels)
            self._poll_timer.start(200)

        def _create_flags(self):
            """Place two green flags on the timeline scene."""
            timeline = self.studio.timeline
            fps = self.studio.project_fps
            upf = timeline.units_per_frame
            height = max(len(timeline.tracks) * 60, 60)

            playhead_frame = timeline.get_playhead_frame()
            clip_start = self.clip.start_frame
            clip_end = clip_start + self.clip.frame_count

            # Default region: playhead to playhead + 5s, clamped
            start_frame = max(clip_start, playhead_frame)
            end_frame = min(clip_end, start_frame + int(fps * 5))
            if start_frame >= end_frame:
                start_frame = max(clip_start, end_frame - int(fps * 5))
            start_frame = max(clip_start, start_frame)

            self.start_flag = Inpaint.InpaintFlagItem(
                height, self.clip, is_start=True,
            )
            self.start_flag.timeline_view = timeline
            self.start_flag.frame = start_frame
            self.start_flag.setPos(start_frame * upf, 0)

            self.end_flag = Inpaint.InpaintFlagItem(
                height, self.clip, is_start=False,
            )
            self.end_flag.timeline_view = timeline
            self.end_flag.frame = end_frame
            self.end_flag.setPos(end_frame * upf, 0)

            # Link partners
            self.start_flag.partner = self.end_flag
            self.end_flag.partner = self.start_flag

            timeline.scene.addItem(self.start_flag)
            timeline.scene.addItem(self.end_flag)

        def _update_region_labels(self):
            """Refresh the start/end second labels from flag positions."""
            start_s = self.start_flag.get_seconds()
            end_s = self.end_flag.get_seconds()
            self.start_label.setText(f"Start: {start_s:.1f}s")
            self.end_label.setText(f"End: {end_s:.1f}s")

        def _remove_flags(self):
            """Remove flags from the timeline scene."""
            scene = self.studio.timeline.scene
            if self.start_flag.scene() is not None:
                scene.removeItem(self.start_flag)
            if self.end_flag.scene() is not None:
                scene.removeItem(self.end_flag)

        def start_inpaint(self):
            """Gather params and launch the background thread."""
            self.config_fields.update_config()
            model_obj = self.config_fields.config.get('model')
            if not model_obj:
                self.status_label.setText("No model selected")
                return

            start_s = self.start_flag.get_seconds()
            end_s = self.end_flag.get_seconds()
            if end_s <= start_s:
                self.status_label.setText(
                    "Invalid region: end must be after start"
                )
                return

            self.btn_inpaint.setEnabled(False)
            self.status_label.setText("Preparing...")

            self._thread = Inpaint.InpaintThread(
                self.clip.filepath, model_obj, start_s, end_s,
            )
            self._thread.progress.connect(self.on_progress)
            self._thread.finished_inpaint.connect(self.on_finished)
            self._thread.error.connect(self.on_error)
            self._thread.start()

        def on_progress(self, msg):
            self.status_label.setText(msg)

        def on_finished(self, output_path):
            self.status_label.setText(f"Done: {output_path}")
            self.btn_inpaint.setEnabled(True)
            self.clip.set_source_filepath(output_path)
            self._poll_timer.stop()
            self._remove_flags()

        def on_error(self, msg):
            self.status_label.setText(f"Error: {msg}")
            self.btn_inpaint.setEnabled(True)

        def closeEvent(self, event):
            self._poll_timer.stop()
            self._remove_flags()
            if self._thread and self._thread.isRunning():
                self._thread.quit()
                self._thread.wait(3000)
            super().closeEvent(event)

    # -------------------------------------------------------------------
    # Worker thread
    # -------------------------------------------------------------------

    class InpaintThread(QThread):
        """Background thread that runs the inpaint model."""

        progress = Signal(str)
        finished_inpaint = Signal(str)
        error = Signal(str)

        POLL_INTERVAL = 3  # seconds

        def __init__(self, filepath, model_obj, start_s, end_s):
            super().__init__()
            self.filepath = filepath
            self.model_obj = model_obj
            self.start_s = start_s
            self.end_s = end_s

        def run(self):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                output_path = loop.run_until_complete(self._run())
                self.finished_inpaint.emit(output_path)
            except Exception as e:
                self.error.emit(str(e))
            finally:
                loop.close()

        async def _run(self):
            """Execute the full inpaint pipeline."""
            # 1. Prepare model object
            self.progress.emit("Preparing model...")
            model_obj = convert_model_json_to_obj(self.model_obj)
            provider_name = model_obj['provider']
            provider = system.manager.providers.get(provider_name)
            if provider is None:
                raise ValueError(
                    f"Provider '{provider_name}' not found"
                )

            model_s_params = system.manager.models.get_model(model_obj)
            model_obj['model_params'] = {
                **model_obj.get('model_params', {}),
                **model_s_params,
            }
            model_name = model_obj['_model_name']

            # 2. Upload audio file
            self.progress.emit("Uploading audio...")
            audio_url = await self._upload_file(
                provider, provider_name, self.filepath,
            )

            # 3. Detect the audio URL param key from input_schema
            audio_key = self._detect_audio_key(model_obj)
            model_obj['model_params'][audio_key] = audio_url

            # 4. Inject timing params
            start_key, end_key, cast_fn = get_timing_params(
                provider_name, model_name,
            )
            model_obj['model_params'][start_key] = cast_fn(
                self.start_s
            )
            model_obj['model_params'][end_key] = cast_fn(self.end_s)

            # 5. Submit model
            self.progress.emit("Submitting request...")
            stream = await provider.run_model(model_obj)
            for item in stream:
                request_data = json.loads(item)
                break

            request_id = request_data['request_id']
            req_model_name = request_data['model_name']

            # 6. Poll until completed
            self.progress.emit("Processing...")
            while True:
                await asyncio.sleep(self.POLL_INTERVAL)
                status = await provider.get_request_status(
                    req_model_name, request_id,
                )
                st = status.get('status', 'unknown')
                if st == 'completed':
                    break
                elif st == 'failed':
                    raise RuntimeError("Provider reported failure")
                pos = status.get('position')
                if pos is not None:
                    self.progress.emit(
                        f"Queued (position {pos})..."
                    )
                elif st == 'in_progress':
                    self.progress.emit("Generating...")

            # 7. Download result
            self.progress.emit("Downloading result...")
            urls = await provider.get_request_result(
                req_model_name, request_id,
            )
            if not urls:
                raise RuntimeError("No output URLs returned")

            output_path = self._output_path()
            await self._download(urls[0], output_path)
            return output_path

        async def _upload_file(self, provider, provider_name, filepath):
            """Upload the audio file to the provider's CDN."""
            if hasattr(provider, 'upload_file'):
                return await provider.upload_file(filepath)

            # Fallback to fal_client for providers without upload
            import fal_client
            api_key = self.model_obj.get('model_params', {}).get(
                'api_key', ''
            )
            if api_key:
                os.environ['FAL_API_KEY'] = api_key
            return fal_client.upload_file(filepath)

        def _detect_audio_key(self, model_obj):
            """Find the input_schema field of type media_upload."""
            metadata_str = None
            try:
                from utils import sql
                opts = convert_model_json_to_obj(model_obj)
                metadata_str = sql.get_scalar("""
                    SELECT metadata FROM models
                    WHERE COALESCE(
                        json_extract(config, '$._model_name'),
                        json_extract(config, '$.model_name')
                    ) = ?
                    AND kind = ?
                    AND provider_plugin = ?
                """, (
                    opts['_model_name'],
                    opts['kind'],
                    opts['provider'],
                ))
            except Exception:
                pass

            if metadata_str:
                try:
                    metadata = json.loads(metadata_str)
                    for field in metadata.get('input_schema', []):
                        if field.get('type') == 'media_upload':
                            return field['key']
                except (json.JSONDecodeError, KeyError):
                    pass

            return 'audio_url'

        def _output_path(self):
            """Build output filepath next to the original."""
            base, ext = os.path.splitext(self.filepath)
            return f"{base}_inpainted{ext}"

        async def _download(self, url, dest):
            """Download a URL to a local file."""
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    with open(dest, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(
                            8192
                        ):
                            f.write(chunk)