from PySide6.QtCore import Qt, QPointF


class CanvasTool:
    """
    Base class for image studio canvas tools.

    The canvas forwards mouse events to the active tool, which edits the
    studio's layers through ``self.canvas``. Tools with no editing
    behaviour (select, move, etc.) can use this class directly as a no-op.
    """
    display_name = 'Tool'
    cursor = Qt.ArrowCursor

    def __init__(self, canvas):
        self.canvas = canvas

    def on_press(self, pos: QPointF):
        pass

    def on_move(self, pos: QPointF):
        pass

    def on_release(self):
        pass
