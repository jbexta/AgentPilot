from PySide6.QtWidgets import *
from PySide6.QtGui import Qt
from typing_extensions import override

from gui.util import CVBoxLayout, CHBoxLayout
from gui.widgets.config_widget import ConfigWidget


class ConfigJoined(ConfigWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        layout_type = kwargs.get('layout_type', 'vertical')
        self.propagate = kwargs.get('propagate', True)
        self.resizable = kwargs.get('resizable', False)
        self.layout = CVBoxLayout(self) if layout_type == 'vertical' else CHBoxLayout(self)

        if self.resizable:
            splitter_orientation = Qt.Horizontal if layout_type == 'horizontal' else Qt.Vertical
            self.splitter = QSplitter(splitter_orientation)
            self.splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.splitter.setChildrenCollapsible(False)
            self.layout.addWidget(self.splitter)

        self.widgets = kwargs.get('widgets', [])
        self.add_stretch_to_end = kwargs.get('add_stretch_to_end', False)
        # self.user_editable = True

    @override
    def build_schema(self):
        for widget in self.widgets:
            if hasattr(widget, 'build_schema'):
                widget.build_schema()

            if self.resizable:
                self.splitter.addWidget(widget)
            else:
                self.layout.addWidget(widget)

        if self.add_stretch_to_end:
            self.layout.addStretch(1)
        # if hasattr(self, 'after_init'):
        self.after_init()

    @override
    def load(self):
        for widget in self.widgets:
            if hasattr(widget, 'load'):
                widget.load()

    @override
    def get_config(self):
        config = {}
        for widget in self.widgets:
            if not getattr(widget, 'propagate', True) or not hasattr(widget, 'get_config'):
                continue
            cc = widget.get_config()
            config.update(cc)
        return config