from core.actions.base import UndoableAction
from utils.helpers import set_module_type

from plugins.studio.actions.base import layer_changed, restore_layer, snapshot_layer


def record_layer_edit(studio, layer, before):
    """Record an edit to a single layer given a pixel snapshot taken before the edit,
    called from `ImageCanvas.mouseReleaseEvent` and workflow result handlers.
    No-op if the layer didn't actually change."""
    if not layer_changed(layer, before):
        return
    studio.undo_history.record(LayerEditAction(
        studio=studio, layer=layer, before=before, after=snapshot_layer(layer, pixels=True)))


@set_module_type('Actions')
class LayerEditAction(UndoableAction):
    """Records a pixel/position change to a single studio layer (brush and eraser
    strokes, move-tool drags, workflow results), so it can be restored on undo/redo."""
    label = 'Edit layer'

    def undo(self):
        self._apply(self.data['before'])

    def redo(self):
        self._apply(self.data['after'])

    def _apply(self, state):
        studio = self.data['studio']
        restore_layer(self.data['layer'], state)
        studio.layers_panel.refresh_layers()
        studio.canvas.update_display()
