from gui.util import IconButton


class Button(IconButton):
    def __init__(self, parent, **kwargs):
        clicked_method = kwargs.pop('clicked', None)
        if clicked_method:
            if isinstance(clicked_method, str):
                kwargs['target'] = getattr(parent, clicked_method, None)
            elif callable(clicked_method):
                kwargs['target'] = clicked_method
        super().__init__(parent=parent, **kwargs)