import asyncio
import json

import shiboken6
from PySide6.QtCore import QTimer

from gui import system
from gui.gui_utils.helpers import find_attribute
from plugins.workflows.utils.runs import BaseRunManager
from plugins.workflows.utils.download import download_url_to_file
from utils.helpers import display_message


def project_key(studio):
    return getattr(studio, 'current_file_path', None) or f'studio:{id(studio)}'


def resolve_gen_key(widget):
    """Return ((project, member_id), studio) identifying the clip a generation
    started from `widget` targets. `GenerateWidget` and its sibling
    `MultiPreview` resolve to the same key. Outside a studio the key anchors on
    the media settings widget instead and `studio` is None."""
    studio = None
    anchor = widget
    w = getattr(widget, 'parent', None)
    while w is not None:
        if hasattr(w, 'multi_preview') and anchor is widget:
            anchor = w
        if hasattr(w, 'timeline') and hasattr(w.timeline, 'clips'):
            studio = w
            break
        w = getattr(w, 'parent', None)

    member_id = str(find_attribute(widget, 'member_id'))
    if studio is not None:
        return (project_key(studio), member_id), studio
    return (f'widget:{id(anchor)}', member_id), None


class MediaGen:
    def __init__(self, studio=None):
        self.studio = studio
        self.task = None
        self.status = ''
        self.pending = []  # serializable {'request_id', 'model_name', 'provider'}
        self.timers = {}  # request_id: QTimer


class MediaGenManager(BaseRunManager):
    """Tracks media generations by (project, clip id): owns the submit task and
    the poll timers so they survive clip reselection, routes status/results to
    whichever MultiPreview currently displays the clip, and persists results
    into the clip config (marking it unread) when none does."""

    sidebar_button = 'videos'
    POLL_INTERVAL_MS = 3000

    def __init__(self):
        super().__init__()
        self.gens = {}  # key: MediaGen

    def is_running(self, key):
        gen = self.gens.get(key)
        if gen is None:
            return False
        return (gen.task is not None and not gen.task.done()) or bool(gen.timers)

    def pending_for(self, key):
        gen = self.gens.get(key)
        return list(gen.pending) if gen else []

    def is_clip_unread(self, studio, member_id):
        return (project_key(studio), str(member_id)) in self.unread

    def attach(self, widget, key, studio=None):
        """Register `widget` as the display for `key`, replay the current
        status text and clear the clip's unread badge."""
        was_unread = key in self.unread
        self.register_display(key, widget)
        gen = self.gens.get(key)
        if gen and gen.status:
            widget.show_status(gen.status)
        if was_unread:
            clip = self._get_clip(studio, key[1])
            if clip is not None:
                clip.update()

    def generate(self, widget):
        model_obj = widget.get_current_model()
        if not model_obj:
            return
        key, studio = resolve_gen_key(widget)
        if self.is_running(key):
            return
        gen = MediaGen(studio)
        self.gens[key] = gen
        gen.task = asyncio.ensure_future(self._do_generate(key, model_obj))
        self.changed.emit()

    async def _do_generate(self, key, model_obj):
        from plugins.workflows.widgets.generate_widget import resolve_media_sources
        gen = self.gens[key]
        self._set_status(key, 'Preparing...')
        try:
            await resolve_media_sources(model_obj, gen.studio, key[1])
            stream = await system.manager.models.run_model(model_obj=model_obj)
            msg_json = None
            for item in stream:
                msg_json = json.loads(item)
                break
            if not msg_json:
                self._finish(key, 'No response from model')
            elif 'filepath' in msg_json:
                self._deliver_files(key, [msg_json['filepath']])
            elif 'request_id' in msg_json and 'model_name' in msg_json:
                self._start_poll(key, {
                    'request_id': msg_json['request_id'],
                    'model_name': msg_json['model_name'],
                    'provider': model_obj.get('provider'),
                })
                self._set_status(key, 'Queued...')
                self._persist_pending(key)
            else:
                self._finish(key, 'Unrecognized model response')
        except Exception as e:
            display_message(f"Generation failed: {e}")
            self._finish(key, 'Failed')

    def ensure_polling(self, key, studio, pending):
        """Adopt saved pending requests (from clip config) that aren't already
        being polled — e.g. after an app restart."""
        gen = self.gens.get(key)
        if gen is None:
            gen = MediaGen(studio)
            self.gens[key] = gen
        elif gen.studio is None:
            gen.studio = studio
        for ctx in pending:
            request_id = ctx.get('request_id')
            if request_id and request_id not in gen.timers:
                self._start_poll(key, dict(ctx))

    def _start_poll(self, key, ctx):
        gen = self.gens[key]
        if ctx not in gen.pending:
            gen.pending.append(ctx)
        timer = QTimer(self)
        timer.timeout.connect(
            lambda: asyncio.ensure_future(self._poll_tick(key, ctx, timer)))
        timer.start(self.POLL_INTERVAL_MS)
        gen.timers[ctx['request_id']] = timer
        asyncio.ensure_future(self._poll_tick(key, ctx, timer))

    async def _poll_tick(self, key, ctx, timer):
        gen = self.gens.get(key)
        if gen is None or gen.timers.get(ctx['request_id']) is not timer:
            timer.stop()
            return

        provider = system.manager.providers.get(ctx['provider'])
        if provider is None:
            self._stop_poll(key, ctx, timer, keep_pending=True)
            self._finish(key, f"Provider '{ctx['provider']}' not found")
            return

        try:
            status = await provider.get_request_status(ctx['model_name'], ctx['request_id'])
        except Exception as e:
            self._stop_poll(key, ctx, timer, keep_pending=True)
            self._finish(key, f"Poll error: {e}")
            return

        s = status.get('status')
        if s == 'queued':
            self._set_status(key, f"Queued (pos: {status.get('position', '?')})")
        elif s == 'in_progress':
            self._set_status(key, "Generating...")
        elif s == 'failed':
            self._stop_poll(key, ctx, timer)
            self._persist_pending(key)  # drop the dead request from saved config
            self._finish(key, 'Failed')
        elif s == 'completed':
            self._stop_poll(key, ctx, timer)
            self._set_status(key, 'Downloading...')
            try:
                media_urls = await provider.get_request_result(ctx['model_name'], ctx['request_id'])
                paths = [p for url in media_urls or []
                         if (p := await download_url_to_file(url)) is not None]
                if paths:
                    self._deliver_files(key, paths)
                else:
                    self._finish(key, 'No media in response')
            except Exception as e:
                self._finish(key, f"Error: {e}")
        # Unknown status — keep waiting

    def _stop_poll(self, key, ctx, timer, keep_pending=False):
        timer.stop()
        gen = self.gens.get(key)
        if gen:
            gen.timers.pop(ctx['request_id'], None)
            if not keep_pending and ctx in gen.pending:
                gen.pending.remove(ctx)

    def _set_status(self, key, text):
        gen = self.gens.get(key)
        if gen:
            gen.status = text
        widget = self.get_display(key)
        if widget:
            widget.show_status(text)

    def _deliver_files(self, key, paths):
        """Route finished files to the attached preview, or persist them into
        the clip config and mark the clip unread."""
        gen = self.gens.get(key)
        widget = self.get_display(key)
        results = [{'filepath': p} for p in paths]
        if widget and widget.isVisible():
            widget.show_status('')
            widget.set_results(results)
            self._finish(key)
            return

        clip = self._get_clip(gen.studio if gen else None, key[1])
        if clip is not None:
            clip.member_config['preview.results'] = results
            clip.member_config['preview.pending'] = list(gen.pending)
            gen.studio.update_config()
            self.unread.add(key)
            clip.update()
        self._finish(key)

    def _persist_pending(self, key):
        """Save the pending request list so a submitted generation survives an
        app restart: through the attached preview's config chain if displayed,
        else directly into the clip config."""
        gen = self.gens.get(key)
        widget = self.get_display(key)
        if widget:
            widget._save_config()
            return
        clip = self._get_clip(gen.studio if gen else None, key[1])
        if clip is not None:
            clip.member_config['preview.pending'] = list(gen.pending)
            gen.studio.update_config()

    def _finish(self, key, status=''):
        """Drop the gen if nothing is still pending; a non-empty `status` is a
        terminal message left visible on the display. A gen with pending-but-
        unpolled requests (transient poll errors) is kept so the pending list
        still serializes into the clip config."""
        self._set_status(key, status)
        gen = self.gens.get(key)
        if gen and not gen.timers and not gen.pending:
            self.gens.pop(key, None)
        self.changed.emit()

    def _get_clip(self, studio, member_id):
        if studio is None or not shiboken6.isValid(studio):
            return None
        return studio.timeline.clips.get(member_id)


_manager = None


def get_gen_manager() -> MediaGenManager:
    global _manager
    if _manager is None:
        _manager = MediaGenManager()
    return _manager
