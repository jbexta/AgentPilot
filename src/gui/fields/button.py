from src.gui.util import IconButton


class Button(IconButton):
    def __init__(self, parent, **kwargs):
        # kwargs.pop('text', None)  # Remove 'text' argument if it exists
        super().__init__(parent=parent, **kwargs)
