"""
Undo/redo history for studio editors, mirroring the app-wide system in
`core.actions.base`. Unlike the app-wide system, each studio owns its own
`UndoHistory` instance, and actions hold live objects (layers, PIL images),
so history is kept in memory only and never persisted.
"""
from PIL import ImageChops

MAX_HISTORY = 30

LAYER_PROPS = ('name', 'visible', 'locked', 'opacity', 'blend_mode', 'x', 'y')


def snapshot_layer(layer, pixels=False):
    """Capture a layer's properties (and optionally its pixels) into a state dict."""
    state = {prop: getattr(layer, prop) for prop in LAYER_PROPS}
    if pixels:
        state['image'] = layer.image.copy()
    return state


def restore_layer(layer, state):
    """Apply a state dict captured by `snapshot_layer` back onto the layer."""
    for prop in LAYER_PROPS:
        setattr(layer, prop, state[prop])
    if 'image' in state:
        # assign a copy so in-place edits (e.g. eraser) can't corrupt the stored snapshot
        layer.image = state['image'].copy()
        layer.width, layer.height = layer.image.size


def layer_changed(layer, state):
    """True if the layer differs from a pixel-inclusive state dict."""
    if any(getattr(layer, prop) != state[prop] for prop in LAYER_PROPS):
        return True
    before = state['image']
    if before.size != layer.image.size:
        return True
    return ImageChops.difference(before, layer.image).getbbox() is not None


class UndoHistory:
    def __init__(self, on_record=None):
        self._undo_stack = []
        self._redo_stack = []
        self._replaying = False
        self._on_record = on_record

    @property
    def replaying(self):
        return self._replaying

    def record(self, action):
        if self._replaying:
            return
        if (self._undo_stack and type(self._undo_stack[-1]) is type(action)
                and action.merge_with(self._undo_stack[-1].data)):
            self._undo_stack[-1] = action
        else:
            self._undo_stack.append(action)
            del self._undo_stack[:-MAX_HISTORY]
        self._redo_stack.clear()
        if self._on_record:
            self._on_record()

    def undo(self):
        self._replay(self._undo_stack, self._redo_stack, 'undo')

    def redo(self):
        self._replay(self._redo_stack, self._undo_stack, 'redo')

    def _replay(self, pop_stack, push_stack, method_name):
        if not pop_stack:
            return
        action = pop_stack.pop()
        self._replaying = True
        try:
            getattr(action, method_name)()
        except Exception:
            # never let a failed replay propagate into the Qt event loop (kills the app)
            import traceback
            traceback.print_exc()
        finally:
            self._replaying = False
        push_stack.append(action)

    def next_undo_label(self):
        """Label of the action that would be undone next, or None if nothing to undo."""
        return self._undo_stack[-1].label if self._undo_stack else None

    def next_redo_label(self):
        """Label of the action that would be redone next, or None if nothing to redo."""
        return self._redo_stack[-1].label if self._redo_stack else None

    def clear(self):
        self._undo_stack.clear()
        self._redo_stack.clear()
