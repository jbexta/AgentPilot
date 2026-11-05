import asyncio

import shiboken6
from PySide6.QtCore import QObject, Signal


class BaseRunManager(QObject):
    """Shared skeleton for managers that track background work by key, route
    output to whichever widget currently displays that key, and keep unread
    state for keys that finished while not visible."""

    changed = Signal()  # work started/finished, or unread state changed
    sidebar_button = None  # main-pages key whose button gets the notification dot

    def __init__(self):
        super().__init__()
        self.displays = {}  # key: widget
        self.unread = set()
        self.changed.connect(self._update_sidebar_dot)

    def get_display(self, key):
        widget = self.displays.get(key)
        if widget is not None and not shiboken6.isValid(widget):
            self.displays.pop(key, None)
            return None
        return widget

    def register_display(self, key, widget):
        """Point `key` at `widget`, dropping the widget's old registrations,
        and clear the key's unread state."""
        for k in [k for k, w in self.displays.items() if w is widget]:
            del self.displays[k]
        self.displays[key] = widget

        if key in self.unread:
            self.unread.discard(key)
            self.changed.emit()

    def attention_keys(self):
        """Keys needing the user's attention, shown as notification dots."""
        return set(self.unread)

    def _update_sidebar_dot(self):
        from gui.gui_utils.helpers import find_main
        main = find_main()
        sidebar = getattr(getattr(main, 'main_pages', None), 'settings_sidebar', None)
        button = sidebar.page_buttons.get(self.sidebar_button) if sidebar else None
        if button:
            button.notification_dot = len(self.attention_keys()) > 0
            button.update()


class WorkflowRun:
    def __init__(self, workflow):
        self.workflow = workflow
        self.stream_tail = {}  # (role, full_member_id): un-persisted streamed text
        self.pending_confirms = {}  # tool_call_id: (Future resolving to approved bool, label to display)


class WorkflowRunManager(BaseRunManager):
    """Tracks live workflow runs by root context id."""

    sidebar_button = 'contexts'

    def __init__(self):
        super().__init__()
        self.runs = {}  # context_id: WorkflowRun
        self.errors = {}  # context_id: error of its latest run, if it raised

    def is_running(self, context_id):
        return context_id in self.runs

    def attention_keys(self):
        awaiting = {context_id for context_id, run in self.runs.items() if run.pending_confirms}
        return super().attention_keys() | awaiting

    def attach(self, widget):
        """Register `widget` as the display for its workflow's context, replay any
        in-flight stream tail and restore the responding UI state."""
        context_id = widget.workflow.context_id
        self.register_display(context_id, widget)

        run = self.runs.get(context_id)
        if run:
            for (role, member_id), text in run.stream_tail.items():
                widget.new_sentence(role, member_id, text)
        widget.input_widget.send_button.update_icon(is_generating=run is not None)

    async def start(self, workflow, from_member_id=None, feed_back=False, notify=True):
        """Run and track a workflow. `notify=False` for runs whose result is
        delivered by the caller, so finishing undisplayed isn't "unread"."""
        context_id = workflow.ensure_context()
        if context_id in self.runs:
            return
        self.runs[context_id] = WorkflowRun(workflow)
        self.errors.pop(context_id, None)
        self.changed.emit()
        try:
            await asyncio.create_task(workflow.behaviour.start(from_member_id, feed_back=feed_back))
        except Exception as e:
            self.errors[context_id] = str(e)
            raise
        finally:
            self.runs.pop(context_id, None)
            widget = self.get_display(context_id)
            displayed = (
                widget is not None
                and widget.isVisible()
                and getattr(widget.workflow, 'context_id', None) == context_id
            )
            if notify and not displayed:
                self.unread.add(context_id)
            self.changed.emit()

    def stop(self, context_id):
        run = self.runs.get(context_id)
        if run:
            run.workflow.behaviour.stop()
            self.reject_pending(context_id)

    def request_confirm(self, context_id, tool_call_id, label=''):
        """A Future the user resolves by approving or rejecting a tool call,
        or None when the context has no tracked run to approve it in.
        Notifies the user when the context isn't on screen."""
        run = self.runs.get(context_id)
        if run is None:
            return None
        future = asyncio.get_running_loop().create_future()
        run.pending_confirms[tool_call_id] = (future, label)
        widget = self.get_display(context_id)
        if widget is None or not widget.isVisible():
            from utils import sql
            from utils.helpers import display_message
            chat_name = sql.get_scalar("SELECT name FROM contexts WHERE id = ?", (context_id,)) or 'A chat'
            display_message(
                message=f'{chat_name} is waiting for approval: {label}',
                title='Approval needed',
            )
        self.changed.emit()
        return future

    def resolve_confirm(self, context_id, tool_call_id, approved):
        run = self.runs.get(context_id)
        future, _ = run.pending_confirms.pop(tool_call_id, (None, '')) if run else (None, '')
        if future is None:
            return
        if not future.done():
            future.set_result(approved)
        self.changed.emit()

    def reject_pending(self, context_id):
        run = self.runs.get(context_id)
        for tool_call_id in list(run.pending_confirms if run else []):
            self.resolve_confirm(context_id, tool_call_id, approved=False)

    def confirm_label(self, context_id, tool_call_id):
        run = self.runs.get(context_id)
        return run.pending_confirms.get(tool_call_id, (None, ''))[1] if run else ''

    def is_awaiting_confirm(self, context_id, tool_call_id=None):
        run = self.runs.get(context_id)
        pending = run.pending_confirms if run else {}
        return bool(pending) if tool_call_id is None else tool_call_id in pending

    def on_chunk(self, context_id, role, member_id, chunk):
        run = self.runs.get(context_id)
        if run is not None:
            key = (role, member_id)
            run.stream_tail[key] = run.stream_tail.get(key, '') + chunk
        widget = self.get_display(context_id)
        if widget:
            widget.new_sentence(role, member_id, chunk)

    def clear_tail(self, context_id, member_id, role=None):
        """Drop persisted stream text from the replay tail: one (role, member)
        entry when `role` is given, else every entry for the member."""
        run = self.runs.get(context_id)
        if run:
            for key in [k for k in run.stream_tail if k[1] == member_id and role in (None, k[0])]:
                del run.stream_tail[key]


_manager = None


def get_run_manager() -> WorkflowRunManager:
    global _manager
    if _manager is None:
        _manager = WorkflowRunManager()
    return _manager
