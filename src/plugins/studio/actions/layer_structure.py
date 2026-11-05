from functools import wraps

from core.actions.base import UndoableAction
from utils.helpers import set_module_type

from plugins.studio.actions.base import restore_layer, snapshot_layer


def snapshot_doc(studio, pixels=False):
    """Capture the document structure: layer order, current layer and per-layer states."""
    return {
        'layers': list(studio.layers),
        'current': studio.current_layer,
        'states': {layer: snapshot_layer(layer, pixels=pixels) for layer in studio.layers},
    }


def doc_changed(before, after):
    if before['layers'] != after['layers'] or before['current'] is not after['current']:
        return True
    return any(
        before['states'][layer] != after['states'][layer]
        for layer in after['layers'] if layer in before['states']
    )


def records_doc(pixels=False, merge_key=None):
    """Decorator for studio/panel methods that mutate the document: snapshots the
    document around the call and records a `LayerStructureAction` if anything changed.
    Use `pixels=True` for operations that rewrite layer pixels (merge, flatten).
    Works on methods of `ImageStudio` itself or of any object with a `.studio` attribute."""
    def decorate(fn):
        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            studio = getattr(self, 'studio', self)
            history = studio.undo_history
            if history.replaying:
                return fn(self, *args, **kwargs)
            before = snapshot_doc(studio, pixels=pixels)
            result = fn(self, *args, **kwargs)
            after = snapshot_doc(studio, pixels=pixels)
            if doc_changed(before, after):
                history.record(LayerStructureAction(
                    studio=studio, before=before, after=after, merge_key=merge_key))
            return result
        return wrapper
    return decorate


@set_module_type('Actions')
class LayerStructureAction(UndoableAction):
    """Records a document-level change: layer order, add/delete, selection, layer
    properties, and (for merge/flatten style operations) layer pixels.
    Rapid consecutive changes to the same target (e.g. opacity slider drags) merge
    into one action via `merge_key`."""
    label = 'Modify layers'

    def merge_with(self, prev_data):
        if (self.data.get('merge_key') and prev_data.get('merge_key') == self.data['merge_key']
                and prev_data['after']['current'] is self.data['before']['current']):
            self.data['before'] = prev_data['before']
            return True
        return False

    def undo(self):
        self._apply(self.data['before'])

    def redo(self):
        self._apply(self.data['after'])

    def _apply(self, snap):
        studio = self.data['studio']
        studio.layers[:] = snap['layers']
        studio.current_layer = snap['current']
        for layer, state in snap['states'].items():
            restore_layer(layer, state)
        studio.layers_panel.refresh_layers()
        studio.canvas.update_display()
