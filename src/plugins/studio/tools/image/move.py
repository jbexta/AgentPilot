from PySide6.QtCore import Qt, QPointF

from plugins.studio.tools.image.base import CanvasTool
from utils.helpers import set_module_type


@set_module_type('Image_tools')
class Move(CanvasTool):
    display_name = 'Move'
    cursor = Qt.SizeAllCursor

    def __init__(self, canvas):
        super().__init__(canvas)
        self.start_pos = None
        self.start_layer_pos = None

    def on_press(self, pos: QPointF):
        """Start dragging the current layer."""
        layer = self.canvas.studio.current_layer
        if not layer or layer.locked:
            return

        self.start_pos = pos
        self.start_layer_pos = (layer.x, layer.y)

    def on_move(self, pos: QPointF):
        """Offset the layer by the drag distance from the press point."""
        layer = self.canvas.studio.current_layer
        if not layer or self.start_pos is None:
            return

        layer.x = self.start_layer_pos[0] + int(pos.x() - self.start_pos.x())
        layer.y = self.start_layer_pos[1] + int(pos.y() - self.start_pos.y())
        self.canvas.update_display()

    def on_release(self):
        self.start_pos = None
        self.start_layer_pos = None
