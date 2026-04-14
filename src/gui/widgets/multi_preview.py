import asyncio
import os
import tempfile

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QWidget, QLabel, QSizePolicy, QPushButton,
)

from src.gui.util import CHBoxLayout, CVBoxLayout
from utils.helpers import download_url_to_file, get_media_preview_class


class MultiPreview(QWidget):
    """Single-row multi-media preview with dynamic resizing."""

    POLL_INTERVAL_MS = 3000
    PREVIEW_MIN_WIDTH = 80
    PREVIEW_MIN_HEIGHT = 80

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.parent = parent
        self.main_layout = CVBoxLayout(self)

        self.preview_row = QWidget(self)
        self.layout = CHBoxLayout(self.preview_row)
        self.layout.setSpacing(5)
        self.main_layout.addWidget(self.preview_row)

        self.use_button = QPushButton("Use", self)
        self.use_button.setFixedHeight(24)
        self.use_button.setFixedWidth(0)
        self.use_button.clicked.connect(self._on_use_clicked)

        self.main_layout.addWidget(self.use_button)

        self.setMaximumHeight(230)
        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Minimum,
        )

        self._previews = []      # list of preview widgets
        self._filepaths = {}     # preview widget -> filepath
        self._selected = None    # currently selected preview widget
        self._poll_timers = []
        self._poll_contexts = []  # serializable poll context dicts

        self._poll_label = QLabel(self)
        self._poll_label.setMaximumWidth(250)
        self._poll_label.setStyleSheet(
            "color: #aaa; padding: 8px; font-style: italic;"
        )
        self._poll_label.setVisible(False)
        self.layout.addWidget(self._poll_label)

        self.conf_namespace = 'preview'
        self.propagate_config = True
        self.config = {}

        self.hide()

    def get_config(self):
        """Return preview state for config serialization."""
        results = [
            {'filepath': fp} for fp in self._filepaths.values()
        ]
        return {
            'preview.results': results,
            'preview.pending': list(self._poll_contexts),
        }

    def load_config(self, json_config=None):
        """Load preview config from *json_config* or parent config."""
        source = json_config if json_config is not None \
            else getattr(self.parent, 'config', {})
        self.config = {
            k: v for k, v in source.items()
            if k.startswith('preview.')
        }

    def load(self):
        """Restore previews and resume polling from saved config."""
        results = self.config.get('preview.results', [])
        pending = self.config.get('preview.pending', [])
        combined = results + pending
        if combined:
            self.set_results(combined, _save=False)

    def _save_config(self):
        """Bubble config save up to the parent widget."""
        if hasattr(self.parent, 'update_config'):
            self.parent.update_config()

    def set_results(self, results, _save=True):
        """Accept a list of result dicts and display them.

        Parameters
        ----------
        results : list[dict]
            Each dict is one of:
            - ``{'filepath': str}``
            - ``{'url': str}``
            - ``{'request_id': str, 'model_name': str,
                  'provider': str}``
        _save : bool
            Whether to persist config after processing.  Set to
            ``False`` when restoring from saved config to avoid a
            redundant write.
        """
        self._clear()
        self.show()

        for result in results:
            if 'filepath' in result:
                self._show_preview(result['filepath'])
            elif 'url' in result:
                raise NotImplementedError("")
                # asyncio.ensure_future(
                #     self._download_and_show(result['url'])
                # )
            elif 'request_id' in result and 'model_name' in result:
                self._start_polling(
                    result['request_id'],
                    result['model_name'],
                    result.get('provider'),
                )

        if _save:
            self._save_config()

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def _start_polling(self, request_id, model_name, provider_name):
        """Show the status label and begin polling for *request_id*."""
        self._poll_label.setText("Queued...")
        self._poll_label.setVisible(True)

        poll_ctx = {
            'request_id': request_id,
            'model_name': model_name,
            'provider': provider_name,
        }
        self._poll_contexts.append(poll_ctx)

        ctx = {
            'request_id': request_id,
            'model_name': model_name,
            'provider_name': provider_name,
            'poll_ctx': poll_ctx,
        }

        timer = QTimer(self)
        timer.timeout.connect(
            lambda: asyncio.ensure_future(
                self._poll_tick(ctx, timer)
            )
        )
        timer.start(self.POLL_INTERVAL_MS)
        self._poll_timers.append(timer)

        # Fire an immediate first poll
        asyncio.ensure_future(self._poll_tick(ctx, timer))

    def _get_provider(self, provider_name):
        """Resolve a provider instance by name.

        Returns ``None`` if the provider is not found.
        """
        from gui import system
        return system.manager.providers.get(provider_name)

    async def _poll_tick(self, ctx, timer):
        """Single poll iteration for a pending request."""
        request_id = ctx['request_id']
        model_name = ctx['model_name']

        self._poll_label.setToolTip("")
        provider = self._get_provider(ctx['provider_name'])
        if provider is None:
            self._poll_label.setText(
                f"Provider '{ctx['provider_name']}' not found"
            )
            timer.stop()
            # if ctx.get('poll_ctx') in self._poll_contexts:
            #     self._poll_contexts.remove(ctx['poll_ctx'])
            # self._save_config()
            return

        try:
            status = await provider.get_request_status(
                model_name, request_id
            )
        except Exception as e:
            self._poll_label.setText(f"Poll error: {e}")
            self._poll_label.setToolTip(f"Poll error: {e}")
            timer.stop()
            # if ctx.get('poll_ctx') in self._poll_contexts:
            #     self._poll_contexts.remove(ctx['poll_ctx'])
            # self._save_config()
            return

        s = status.get('status')
        if s == 'queued':
            pos = status.get('position', '?')
            self._poll_label.setText(f"Queued (pos: {pos})")
            return
        elif s == 'in_progress':
            self._poll_label.setText("Generating...")
            return
        elif s == 'completed':
            timer.stop()
            if ctx.get('poll_ctx') in self._poll_contexts:
                self._poll_contexts.remove(ctx['poll_ctx'])
            self._poll_label.setText("Downloading...")
        elif s == 'failed':
            self._poll_label.setText("Failed")
            return
        else:
            # Unknown status — keep waiting
            return

        # Completed — fetch result URLs from provider
        try:
            media_urls = await provider.get_request_result(
                model_name, request_id
            )
            if media_urls:
                await self._download_and_show_files(
                    media_urls  # [0], ctx['index'], replace=label
                )
            else:
                self._poll_label.setText("No media in response")
        except Exception as e:
            self._poll_label.setText(f"Error: {e}")
            self._poll_label.setToolTip(f"Error: {e}")

    # ------------------------------------------------------------------
    # Download helpers
    # ------------------------------------------------------------------

    async def _download_and_show_files(self, urls):
        """Download all *urls* then display with correct layout."""
        paths = []
        for url in urls:
            local_path = await self._download_file(url)
            if local_path is not None:
                paths.append(local_path)

        if not paths:
            return

        self._clear()
        for path in paths:
            self._show_preview(path)
        self._save_config()

    async def _download_file(self, url):
        """Download *url* and return the local path.

        Returns ``None`` on failure.
        """
        return await download_url_to_file(url)

    # ------------------------------------------------------------------
    # Preview display
    # ------------------------------------------------------------------

    def _show_preview(self, local_path):
        """Create and insert a preview widget for *local_path*."""
        ext = os.path.splitext(local_path)[1].lower()

        preview_class = get_media_preview_class(ext=ext)
        if preview_class is None:
            return

        preview = preview_class(self)
        preview.set_filepath(local_path)

        frame = self._SelectableFrame(self)
        frame.setCursor(Qt.PointingHandCursor)
        frame.setMinimumSize(
            self.PREVIEW_MIN_WIDTH,
            self.PREVIEW_MIN_HEIGHT,
        )
        preview.setMinimumSize(
            self.PREVIEW_MIN_WIDTH - 8,
            self.PREVIEW_MIN_HEIGHT - 8,
        )
        frame._layout.addWidget(preview)
        frame.mousePressEvent = (
            lambda e, f=frame: self._select_preview(f)
        )
        frame.mouseDoubleClickEvent = (
            lambda e, f=frame: self._on_double_click(f)
        )
        frame.on_click = lambda f=frame: self._select_preview(f)
        frame.on_double_click = lambda f=frame: self._on_double_click(f)
        frame.install_filter_recursive()

        self._previews.append(frame)
        self._filepaths[frame] = local_path
        self.layout.addWidget(frame)

        self.show()

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _select_preview(self, frame):
        """Select *frame*, deselecting any other."""
        if self._selected is frame:
            return
        if self._selected is not None:
            self._selected.set_selected(False)
        self._selected = frame
        frame.set_selected(True)
        self.use_button.setMaximumWidth(16777215)

    def _on_double_click(self, frame):
        """Select and immediately use the preview."""
        self._select_preview(frame)
        self._on_use_clicked()

    def _on_use_clicked(self):
        """Set the browse path of the parent Settings widget."""
        if self._selected is None:
            return
        filepath = self._filepaths.get(self._selected)
        if filepath is None:
            return
        browse_settings = self.parent.widgets[0]
        if hasattr(browse_settings, 'path_wgt'):
            browse_settings.path_wgt.set_value(filepath)
            browse_settings.update_config()

        # If the model has an audio media_upload field, mute the clip
        self._mute_if_audio_input()
        self._align_audio_if_needed(filepath)

    def _get_audio_input_clip(self):
        """Return (studio, clip) if the model has an active audio input.

        Returns ``None`` if no active audio media_upload is found or
        the clip cannot be resolved.
        """
        try:
            tabs = self.parent.widgets[1]
            model_settings = tabs.pages['Model']
            model_fields = model_settings.widgets[0]
            schema = model_fields.model_wgt.config_widget.schema
        except (AttributeError, KeyError, IndexError):
            return None

        config_widget = model_fields.model_wgt.config_widget
        has_active_audio = False
        for f in schema:
            if (f.get('type') == 'media_upload'
                    and f.get('media_type', 'any')
                    in ('audio', 'any')):
                key = f.get('key', '')
                wgt = getattr(config_widget, f'{key}_wgt', None)
                if wgt and wgt.isVisible() and wgt.get_value():
                    has_active_audio = True
                    break
        if not has_active_audio:
            return None

        member_config_widget = self.parent.parent
        if not hasattr(member_config_widget, 'config_widget'):
            return None
        member_id = member_config_widget.config_widget.member_id
        studio = member_config_widget.parent
        if not hasattr(studio, 'timeline'):
            return None
        clip = studio.timeline.clips.get(member_id)
        if not clip:
            return None
        return studio, clip

    def _mute_if_audio_input(self):
        """Set clip volume to 0 if the model has a visible, non-empty audio media_upload input."""
        result = self._get_audio_input_clip()
        if result is None:
            return
        _studio, clip = result
        clip.member_config['volume'] = 0
        clip.update()

    def _align_audio_if_needed(self, generated_path):
        """Adjust clip start_frame to align generated audio with timeline audio."""
        from utils.media_export import (
            compute_audio_offset,
            render_timeline_audio,
        )

        result = self._get_audio_input_clip()
        if result is None:
            return
        studio, clip = result

        fps = studio.project_fps
        if clip.duration < 0.1:
            return

        # Build clip info list for timeline audio
        clip_infos = []
        for cid, c in studio.timeline.clips.items():
            filepath = c.filepath
            if not filepath or not os.path.isfile(filepath):
                continue
            volume = c.member_config.get('volume', 100)
            clip_infos.append({
                'filepath': filepath,
                'start_time': c.start_time,
                'in_point': c.in_point,
                'duration': c.duration,
                'volume': volume,
            })

        if not clip_infos:
            return

        ref_fd, ref_path = tempfile.mkstemp(suffix='.wav')
        os.close(ref_fd)
        try:
            render_timeline_audio(
                clip_infos,
                clip.start_time,
                clip.duration,
                fps,
                ref_path,
            )
            offset_seconds = compute_audio_offset(
                ref_path, generated_path,
            )
        except Exception:
            return
        finally:
            try:
                os.unlink(ref_path)
            except OSError:
                pass

        if offset_seconds == 0.0:
            return

        offset_frames = round(offset_seconds * fps)
        clip.start_frame = max(0, clip.start_frame - offset_frames)

        ppf = studio.timeline.units_per_frame
        clip.setPos(
            clip.start_frame * ppf,
            clip.track_index * 60,
        )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _clear(self):
        """Remove all current preview widgets and stop timers."""
        for timer in self._poll_timers:
            timer.stop()
        self._poll_timers.clear()
        self._poll_contexts.clear()
        self._poll_label.setVisible(False)

        for preview in self._previews:
            self.layout.removeWidget(preview)
            preview.deleteLater()
        self._previews.clear()
        self._filepaths.clear()
        self._selected = None
        self.use_button.setFixedWidth(0)

    class _SelectableFrame(QWidget):
        """Wrapper that paints a selection border without stylesheets."""
        def __init__(self, parent=None):
            super().__init__(parent)
            self._selected = False
            self._layout = CVBoxLayout(self)
            self._layout.setContentsMargins(2, 2, 2, 2)
            self.on_click = None
            self.on_double_click = None

        def install_filter_recursive(self):
            """Install this frame as event filter on all descendants."""
            for child in self.findChildren(QWidget):
                child.installEventFilter(self)

        def eventFilter(self, obj, event):
            if event.type() == QEvent.MouseButtonPress:
                if self.on_click:
                    self.on_click()
            elif event.type() == QEvent.MouseButtonDblClick:
                if self.on_double_click:
                    self.on_double_click()
            return False

        def set_selected(self, selected):
            self._selected = selected
            self.update()

        def paintEvent(self, event):
            super().paintEvent(event)
            if self._selected:
                painter = QPainter(self)
                pen = QPen(QColor("#4a9fff"), 2)
                painter.setPen(pen)
                painter.drawRect(1, 1, self.width() - 2, self.height() - 2)
                painter.end()