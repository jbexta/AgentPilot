import os
import tempfile

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QWidget, QLabel, QSizePolicy, QPushButton,
)

from gui.gui_utils.layouts import CHBoxLayout, CVBoxLayout
from utils.media import get_media_preview_class
from plugins.workflows.utils.gens import get_gen_manager, resolve_gen_key


class MultiPreview(QWidget):
    """Single-row multi-media preview with dynamic resizing."""

    PREVIEW_MIN_WIDTH = 80
    PREVIEW_MIN_HEIGHT = 80

    def __init__(self, parent=None, on_use=None):
        super().__init__(parent=parent)
        self.parent = parent
        self.on_use = on_use
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

        self.collapsed = False
        self._previews = []      # list of preview widgets
        self._filepaths = {}     # preview widget -> filepath
        self._selected = None    # currently selected preview widget
        self._key = None         # gen manager key, resolved on load
        self._studio = None

        self._poll_label = QLabel(self)
        self._poll_label.setMaximumWidth(250)
        self._poll_label.setObjectName('previewPollLabel')
        self._poll_label.setVisible(False)
        self.layout.addWidget(self._poll_label)

        self.conf_namespace = 'preview'
        self.propagate_config = True
        self.config = {}

        self.hide()

    def show(self):
        if not self.collapsed:
            super().show()

    def set_collapsed(self, collapsed):
        if collapsed == self.collapsed:
            return
        self.collapsed = collapsed
        if collapsed:
            self.hide()
        elif self._previews or self._poll_label.isVisible():
            super().show()

    def get_config(self):
        """Return preview state for config serialization."""
        results = [
            {'filepath': fp} for fp in self._filepaths.values()
        ]
        pending = get_gen_manager().pending_for(self._key) if self._key else []
        return {
            'preview.results': results,
            'preview.pending': pending,
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
        """Restore previews, attach to the gen manager and adopt saved polling."""
        self._key, self._studio = resolve_gen_key(self)
        results = self.config.get('preview.results', [])
        if results:
            self.set_results(results, _save=False)
        manager = get_gen_manager()
        pending = self.config.get('preview.pending', [])
        if pending:
            manager.ensure_polling(self._key, self._studio, pending)
        manager.attach(self, self._key, self._studio)

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

        adopted = False
        for result in results:
            if 'filepath' in result:
                self._show_preview(result['filepath'])
            elif 'url' in result:
                raise NotImplementedError("")
            elif 'request_id' in result and 'model_name' in result:
                if self._key is None:
                    self._key, self._studio = resolve_gen_key(self)
                get_gen_manager().ensure_polling(
                    self._key, self._studio, [{
                        'request_id': result['request_id'],
                        'model_name': result['model_name'],
                        'provider': result.get('provider'),
                    }])
                adopted = True

        if adopted:
            # Callers that pass request results directly (e.g. the workflow
            # results popup) never go through load(), so register as the
            # display here or the finished downloads have nowhere to land.
            get_gen_manager().attach(self, self._key, self._studio)

        if _save:
            self._save_config()

    def show_status(self, text):
        """Display (or clear) generation status text from the gen manager."""
        if text:
            self._poll_label.setText(text)
            self._poll_label.setToolTip(text)
            self._poll_label.setVisible(True)
            self.show()
        else:
            self._poll_label.setVisible(False)

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
        """Invoke the on_use callback, or set the browse path of the parent Settings widget."""
        if self._selected is None:
            return
        filepath = self._filepaths.get(self._selected)
        if filepath is None:
            return
        if self.on_use is not None:
            self.on_use(filepath)
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
        from plugins.workflows.utils.media_export import (
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
        """Remove all current preview widgets."""
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