from PIL import Image, ImageDraw
from PySide6.QtCore import QPointF

from plugins.studio.tools.image.brush import Brush
from utils.helpers import set_module_type


@set_module_type('Image_tools')
class Eraser(Brush):
    display_name = 'Eraser'

    def on_move(self, pos: QPointF):
        """Erase along the stroke by clearing the current layer's alpha."""
        canvas = self.canvas
        if not canvas.temp_draw or not canvas.last_point or not canvas.studio.current_layer:
            return

        x1, y1 = int(canvas.last_point.x()), int(canvas.last_point.y())
        x2, y2 = int(pos.x()), int(pos.y())

        # Create eraser mask
        mask = Image.new('L', (canvas.studio.canvas_width, canvas.studio.canvas_height), 0)
        mask_draw = ImageDraw.Draw(mask)

        radius = canvas.brush_size // 2
        mask_draw.line([x1, y1, x2, y2], fill=255, width=canvas.brush_size)
        mask_draw.ellipse([x2 - radius, y2 - radius, x2 + radius, y2 + radius], fill=255)

        # Apply eraser to current layer directly
        canvas.studio.current_layer.erase(mask)

        canvas.update_display()
