from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QMessageBox

from plugins.studio.tools.image.base import CanvasTool
from utils.helpers import set_module_type


@set_module_type('Image_tools')
class Fill(CanvasTool):
    display_name = 'Fill'

    def on_press(self, pos: QPointF):
        """Fill with foreground color at point."""
        # TODO: Implement flood fill algorithm
        QMessageBox.information(self.canvas, "Fill", "Fill tool not yet implemented")
