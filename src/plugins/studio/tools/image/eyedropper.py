from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor

from plugins.studio.tools.image.base import CanvasTool
from utils.helpers import set_module_type


@set_module_type('Image_tools')
class Eyedropper(CanvasTool):
    display_name = 'Eyedropper'
    cursor = Qt.PointingHandCursor

    def on_press(self, pos: QPointF):
        """Pick color from the composited canvas at point."""
        canvas = self.canvas
        studio = canvas.studio
        x, y = int(pos.x()), int(pos.y())

        if 0 <= x < studio.canvas_width and 0 <= y < studio.canvas_height:
            # Get pixel from composite image
            result = studio.composite_layers(background=(255, 255, 255, 255))
            pixel = result.getpixel((x, y))
            color = QColor(pixel[0], pixel[1], pixel[2], pixel[3])

            studio.foreground_color = color
            studio.update_color_button(studio.fg_color_btn, color)
            canvas.foreground_color = color
