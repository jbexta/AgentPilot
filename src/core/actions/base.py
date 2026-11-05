from contextlib import contextmanager

MAX_HISTORY = 50

_replaying = False
_loaded = False
_capture = None
_undo_stack = []
_redo_stack = []


class UndoableAction:
    label = ''

    def __init__(self, **data):
        self.data = data  # must remain JSON-serializable

    def undo(self):
        pass

    def redo(self):
        pass

    def merge_with(self, prev_data):
        """Try to absorb `prev_data` (the previous entry of the same type) into this
        action's data; return True if merged (the previous entry is then replaced)."""
        return False


def get_action_class(type_name):
    from gui import system
    return system.manager.modules.get_module_class(module_type='actions', module_name=type_name)


def record(action):
    if _replaying:
        return
    entry = {'type': type(action).__module__.split('.')[-1], 'data': action.data}
    if _capture is not None:
        _capture.append(entry)
        return
    if _undo_stack and _undo_stack[-1]['type'] == entry['type'] and action.merge_with(_undo_stack[-1]['data']):
        _undo_stack[-1] = entry
    else:
        _undo_stack.append(entry)
        del _undo_stack[:-MAX_HISTORY]
    _redo_stack.clear()
    flush()  # temp: persist after every record


@contextmanager
def capture():
    """Collect the entries recorded inside the block instead of adding them to
    history, so a caller can wrap them into a single grouped action."""
    global _capture
    prev = _capture
    entries = []
    _capture = entries
    try:
        yield entries
    finally:
        _capture = prev


def _replay(pop_stack, push_stack, method_name):
    global _replaying
    if not pop_stack:
        return
    entry = pop_stack.pop()
    action_class = get_action_class(entry['type'])
    if action_class:
        _replaying = True
        try:
            getattr(action_class(**entry['data']), method_name)()
        except Exception:
            # never let a failed replay propagate into the Qt event loop (kills the app)
            import traceback
            traceback.print_exc()
        finally:
            _replaying = False
    push_stack.append(entry)
    flush()


@contextmanager
def replay_guard(active):
    """Re-apply replay suppression around a callback that was queued during a replay,
    so it can't record a spurious action after the replay call has returned."""
    global _replaying
    prev = _replaying
    _replaying = prev or active
    try:
        yield
    finally:
        _replaying = prev


def _entry_label(entry):
    action_class = get_action_class(entry['type'])
    return getattr(action_class, 'label', None) or entry['type']


def next_undo_label():
    """Label of the action that would be undone next, or None if nothing to undo."""
    return _entry_label(_undo_stack[-1]) if _undo_stack else None


def next_redo_label():
    """Label of the action that would be redone next, or None if nothing to redo."""
    return _entry_label(_redo_stack[-1]) if _redo_stack else None


def undo():
    _replay(_undo_stack, _redo_stack, 'undo')


def redo():
    _replay(_redo_stack, _undo_stack, 'redo')


def load():
    """Build the in-memory stacks from the `undo_history` settings field, called once on startup."""
    global _loaded
    import json
    from utils import sql
    history = sql.get_scalar("SELECT value FROM settings WHERE `field` = 'undo_history'")
    history = json.loads(history) if history else {}
    _undo_stack[:] = history.get('undo', [])
    _redo_stack[:] = history.get('redo', [])
    _loaded = True


def flush():
    """Persist the in-memory stacks to the `undo_history` settings field, called on app close."""
    import json
    from utils import sql
    if not _loaded:  # never overwrite stored history with stacks that were never loaded
        return
    history = json.dumps({'undo': _undo_stack, 'redo': _redo_stack})
    if sql.get_scalar("SELECT COUNT(*) FROM settings WHERE `field` = 'undo_history'"):
        sql.execute("UPDATE settings SET value = ? WHERE `field` = 'undo_history'", (history,))
    else:
        sql.execute("INSERT INTO settings (field, value) VALUES ('undo_history', ?)", (history,))
