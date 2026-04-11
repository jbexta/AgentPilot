"""Reusable Generate button widget.

Provides a ConfigFields subclass with a single Generate button that
runs a model asynchronously and pushes results to the nearest
MultiPreview widget found in the parent chain.

Subclasses must override ``get_current_model()`` to return the
model_obj dict used by ``system.manager.models.run_model``.
"""

import asyncio
import json
import os
import tempfile

from PySide6.QtWidgets import QSizePolicy

from gui import system
from gui.widgets.config_fields import ConfigFields
from gui.util import find_attribute, find_workflow_widget
from utils.helpers import display_message


class GenerateWidget(ConfigFields):
    """Base generate-button widget.

    Schema contains a single Generate button.  Subclasses override
    ``get_current_model()`` to supply the model_obj dict.
    """

    def __init__(self, parent):
        super().__init__(parent=parent, add_stretch_to_end=False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.schema = [
            {
                'text': 'Generate',
                'type': 'button',
                'clicked': '_on_generate_clicked',
                'visibility_predicate':
                    self.generate_button_visibility_predicate,
                'label_position': None,
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
        """Kick off async generation."""
        asyncio.ensure_future(self._do_generate())

    async def _do_generate(self):
        """Run the model and push results to the MultiPreview."""
        model_obj = self.get_current_model()
        if not model_obj:
            return
        self.generate_wgt.setEnabled(False)
        try:
            await self._resolve_media_sources(model_obj)
            stream = await system.manager.models.run_model(
                model_obj=model_obj,
            )
            msg_json = None
            for item in stream:
                msg_json = json.loads(item)
                break
            if msg_json:
                msg_json['provider'] = model_obj.get('provider')
                multi_preview = self._find_multi_preview()
                if multi_preview:
                    multi_preview.set_results([msg_json])
        except Exception as e:
            display_message(f"Generation failed: {e}")
        finally:
            self.generate_wgt.setEnabled(True)

    def _find_multi_preview(self):
        """Walk the parent chain looking for a ``multi_preview`` attr."""
        widget = self.parent
        while widget is not None:
            if hasattr(widget, 'multi_preview'):
                return widget.multi_preview
            widget = getattr(widget, 'parent', None)
        return None

    def _find_studio(self):
        """Walk the parent chain looking for a studio with a timeline."""
        widget = self.parent
        while widget is not None:
            if (hasattr(widget, 'timeline')
                    and hasattr(widget.timeline, 'clips')):
                return widget
            widget = getattr(widget, 'parent', None)
        return None

    async def _resolve_media_sources(self, model_obj):
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
        """
        params = model_obj.get('model_params')
        if not params:
            return

        studio = self._find_studio()
        if not studio:
            return

        member_id = find_attribute(self, 'member_id')
        provider_name = model_obj.get('provider')
        provider = system.manager.providers.get(provider_name)

        for key, value in list(params.items()):
            if not isinstance(value, str):
                continue
            try:
                ref = json.loads(value)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            if not isinstance(ref, dict) or 'source' not in ref:
                continue

            url = await self._render_source(
                ref, studio, member_id, provider,
            )
            if url:
                params[key] = url

    async def _render_source(self, ref, studio, member_id, provider):
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
        from utils.media_export import (
            render_timeline_audio, extract_clip_media,
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

                start_time = target_clip.start_time
                duration = target_clip.duration

                # Build clip info list for all timeline clips
                clip_infos = []
                for cid, clip in studio.timeline.clips.items():
                    filepath = clip.filepath
                    if not filepath or not os.path.isfile(filepath):
                        continue
                    volume = clip.member_config.get('volume', 100)
                    clip_infos.append({
                        'filepath': filepath,
                        'start_time': clip.start_time,
                        'in_point': clip.in_point,
                        'duration': clip.duration,
                        'volume': volume,
                    })

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
                trim = ref.get('trim_to_position', True)

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
