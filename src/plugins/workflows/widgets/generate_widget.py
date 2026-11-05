import asyncio
import json
import os
import tempfile

from PySide6.QtWidgets import QSizePolicy

from gui import system
from gui.widgets.config_fields import ConfigFields
from gui.gui_utils.helpers import find_workflow_widget
from plugins.workflows.utils.gens import get_gen_manager, resolve_gen_key


class GenerateWidget(ConfigFields):
    """Base generate-button widget.

    Schema contains a single Generate button.  Subclasses override
    ``get_current_model()`` to supply the model_obj dict.
    """

    def __init__(self, parent):
        super().__init__(parent=parent, add_stretch_to_end=False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        get_gen_manager().changed.connect(self._refresh_busy)
        self.schema = [
            {
                'text': 'Generate',
                'type': 'button',
                'clicked': '_on_generate_clicked',
                'visibility_predicate':
                    self.generate_button_visibility_predicate,
                'label_position': None,
                'row_key': 'generate',
            },
            {
                'type': 'stretch',
                'row_key': 'generate',
            },
            {
                'key': 'collapse_preview',
                'text': '',
                'type': 'button_toggle',
                'icon_path': ':/resources/icon-arrow-left.png',
                'icon_path_checked': ':/resources/icon-expanded.png',
                'tooltip': 'Collapse preview',
                'tooltip_checked': 'Expand preview',
                'default': False,
                'label_position': None,
                'row_key': 'generate',
            },
        ]

    def get_current_model(self):
        """Return the model_obj dict for generation.

        Must be overridden by subclasses.
        """
        raise NotImplementedError

    def refresh_visibility(self):
        """Hide the entire widget when the generate button is hidden."""
        super().refresh_visibility()
        is_visible = self.generate_button_visibility_predicate()
        self.setVisible(is_visible)

        multi_preview = self._find_multi_preview()
        if multi_preview:
            multi_preview.set_collapsed(
                self.collapse_preview_wgt.isChecked()
            )

    def generate_button_visibility_predicate(self):
        """Show the button only when a workflow is active."""
        workflow_settings = find_workflow_widget(self)
        if not workflow_settings:
            return True  # todo clean patch
        parent_of_workflow_settings = workflow_settings.parent
        return getattr(
            parent_of_workflow_settings, 'workflow', None
        ) is not None

    def _on_generate_clicked(self):
        """Kick off async generation, tracked by the gen manager."""
        multi_preview = self._find_multi_preview()
        if multi_preview and self.collapse_preview_wgt.isChecked():
            self.collapse_preview_wgt.setChecked(False)
        get_gen_manager().generate(self)

    def _refresh_busy(self):
        if not hasattr(self, 'generate_wgt'):
            return
        key, _ = resolve_gen_key(self)
        self.generate_wgt.setEnabled(not get_gen_manager().is_running(key))

    def load(self):
        super().load()
        self._refresh_busy()

    def _find_multi_preview(self):
        """Walk the parent chain looking for a ``multi_preview`` attr."""
        widget = self.parent
        while widget is not None:
            if hasattr(widget, 'multi_preview'):
                return widget.multi_preview
            widget = getattr(widget, 'parent', None)
        return None


async def resolve_media_sources(model_obj, studio, member_id):
    """Resolve timeline/clip source references in model_params.

    Scans ``model_obj['model_params']`` for JSON values containing
    a ``source`` key. Renders the referenced media via ffmpeg,
    uploads the result to the provider CDN, and replaces the
    parameter value with the resulting URL.

    Parameters
    ----------
    model_obj : dict
        The model object whose ``model_params`` may contain source
        references.
    studio : widget or None
        The studio widget with timeline.
    member_id : str or None
        The target clip's member_id.
    """
    params = model_obj.get('model_params')
    if not params or studio is None:
        return

    provider_name = model_obj.get('provider')
    provider = system.manager.providers.get(provider_name)

    async def resolve(value, key):
        if not isinstance(value, str):
            return value
        try:
            ref = json.loads(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            return value
        if not isinstance(ref, dict) or 'source' not in ref:
            return value

        url = await render_source(
            ref, studio, member_id, provider,
        )
        if not url:
            raise ValueError(
                f"Could not resolve the "
                f"'{ref.get('source')}' media source "
                f"for parameter '{key}'"
            )
        return url

    for key, value in list(params.items()):
        # List fields (e.g. Replicate's `reference_audios`) hold a
        # source reference per entry, not a single scalar value.
        if isinstance(value, list):
            params[key] = [await resolve(v, key) for v in value]
        else:
            params[key] = await resolve(value, key)


async def render_source(ref, studio, member_id, provider):
    """Render a single source reference and upload.

    Parameters
    ----------
    ref : dict
        The parsed source reference dict.
    studio : widget
        The studio widget with timeline.
    member_id : str or None
        The target clip's member_id.
    provider : Provider or None
        Provider instance for uploading.

    Returns
    -------
    str or None
        CDN URL of the rendered media, or None on failure.
    """
    from plugins.workflows.utils.media_export import (
        build_audio_clip_infos, render_timeline_audio,
        render_timeline_frame, extract_clip_media,
    )

    target_clip = None
    if member_id and member_id in studio.timeline.clips:
        target_clip = studio.timeline.clips[member_id]

    fps = studio.project_fps
    source_type = ref.get('source')
    tmp_path = None

    try:
        if source_type == 'timeline':
            if not target_clip:
                return None

            if target_clip.member_type == 'image':
                # Composite a single frame at the target clip position
                clip_infos = []
                for cid, clip in studio.timeline.clips.items():
                    filepath = clip.filepath
                    if not filepath or not os.path.isfile(filepath):
                        continue
                    clip_infos.append({
                        'filepath': filepath,
                        'media_type': clip.member_type,
                        'start_frame': clip.start_frame,
                        'in_frame': clip.in_frame,
                        'frame_count': clip.frame_count,
                        'track_index': clip.track_index,
                        'is_disabled': clip.is_disabled,
                        'scale': getattr(clip, 'scale', 1.0),
                        'pos_x': getattr(clip, 'pos_x', 0.0),
                        'pos_y': getattr(clip, 'pos_y', 0.0),
                        'rotation': getattr(clip, 'rotation', 0.0),
                    })

                tmp_fd, tmp_path = tempfile.mkstemp(suffix='.png')
                os.close(tmp_fd)
                await asyncio.to_thread(
                    render_timeline_frame,
                    clip_infos, target_clip.start_frame, fps,
                    studio.project_width, studio.project_height,
                    tmp_path,
                )
            else:
                start_time = target_clip.start_time
                duration = target_clip.duration

                # Serialize every clip, then let the shared export
                # helper drop the silent ones and mix in track volume.
                clip_datas = [{
                    'filepath': clip.filepath,
                    'media_type': clip.member_type,
                    'start_frame': clip.start_frame,
                    'in_frame': clip.in_frame,
                    'frame_count': clip.frame_count,
                    'track_index': clip.track_index,
                    'is_disabled': clip.is_disabled,
                    'volume': clip.member_config.get('volume', 100),
                } for clip in studio.timeline.clips.values()]
                clip_infos = build_audio_clip_infos(
                    clip_datas,
                    studio.track_control_panel.get_config(),
                    fps,
                )

                tmp_fd, tmp_path = tempfile.mkstemp(suffix='.wav')
                os.close(tmp_fd)
                await asyncio.to_thread(
                    render_timeline_audio,
                    clip_infos, start_time, duration, fps, tmp_path,
                )

        elif source_type == 'clip':
            clip_id = ref.get('clip_id')
            if not clip_id or clip_id not in studio.timeline.clips:
                return None

            clip = studio.timeline.clips[clip_id]
            trim = (ref.get('trim_to_position', True)
                    and clip.member_type != 'image')

            if trim and target_clip:
                # Calculate the portion relative to target clip
                clip_start = clip.start_time
                target_start = target_clip.start_time
                target_dur = target_clip.duration

                offset = clip.in_point + max(
                    0, target_start - clip_start
                )
                dur = min(
                    clip.duration,
                    target_dur,
                    clip_start + clip.duration - target_start,
                )
                if dur <= 0:
                    return None
            else:
                offset = clip.in_point
                dur = clip.duration

            media_type = clip.member_type
            ext = '.wav' if media_type == 'audio' else (
                '.mp4' if media_type == 'video' else '.png'
            )
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext)
            os.close(tmp_fd)
            await asyncio.to_thread(
                extract_clip_media,
                clip.filepath, offset, dur, media_type, tmp_path,
            )

        else:
            return None

        # Upload rendered file to CDN
        if provider and hasattr(provider, 'upload_file'):
            url = await provider.upload_file(tmp_path)
            return url

        return None

    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass