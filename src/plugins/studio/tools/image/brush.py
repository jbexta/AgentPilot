from PIL import Image, ImageDraw
from PySide6.QtCore import Qt, QPointF

from plugins.studio.tools.image.base import CanvasTool
from utils.helpers import set_module_type


@set_module_type('Image_tools')
class Brush(CanvasTool):
    display_name = 'Brush'
    cursor = Qt.CrossCursor

    def on_press(self, pos: QPointF):
        """Start a new brush stroke on a temporary layer."""
        canvas = self.canvas
        if not canvas.studio.current_layer:
            return

        canvas.temp_layer = Image.new('RGBA', (canvas.studio.canvas_width, canvas.studio.canvas_height), (0, 0, 0, 0))
        canvas.temp_draw = ImageDraw.Draw(canvas.temp_layer)

        # Draw initial point
        x, y = int(pos.x()), int(pos.y())
        color = (
            canvas.foreground_color.red(),
            canvas.foreground_color.green(),
            canvas.foreground_color.blue(),
            int(255 * canvas.brush_opacity)
        )

        radius = canvas.brush_size // 2
        canvas.temp_draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=color)

    def on_move(self, pos: QPointF):
        """Continue the brush stroke."""
        canvas = self.canvas
        if not canvas.temp_draw or not canvas.last_point:
            return

        # Draw line from last point to current point
        x1, y1 = int(canvas.last_point.x()), int(canvas.last_point.y())
        x2, y2 = int(pos.x()), int(pos.y())

        color = (
            canvas.foreground_color.red(),
            canvas.foreground_color.green(),
            canvas.foreground_color.blue(),
            int(255 * canvas.brush_opacity)
        )

        # Draw line with brush size
        canvas.temp_draw.line([x1, y1, x2, y2], fill=color, width=canvas.brush_size)

        # Draw circle at endpoint for smooth line
        radius = canvas.brush_size // 2
        canvas.temp_draw.ellipse([x2 - radius, y2 - radius, x2 + radius, y2 + radius], fill=color)

        canvas._update_temp_display()

    def on_release(self):
        """Composite the stroke's temporary layer onto the current layer."""
        canvas = self.canvas
        if not canvas.temp_layer or not canvas.studio.current_layer:
            canvas.temp_layer = None
            canvas.temp_draw = None
            return

        canvas.studio.current_layer.stamp(canvas.temp_layer)

        canvas.temp_layer = None
        canvas.temp_draw = None

        canvas.update_display()
