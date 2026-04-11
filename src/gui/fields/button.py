"""
Button field widget for configurable icon buttons.

This module provides a Button field widget that extends IconButton to serve as
a configurable field component. It integrates with the configuration system
while providing icon-based button functionality.
"""

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
