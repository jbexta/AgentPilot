from PySide6.QtWidgets import QWidget, QFrame, QSplitter, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from typing_extensions import override

from gui.util import CVBoxLayout, CHBoxLayout, IconButton
from gui.widgets.config_widget import ConfigWidget
from utils.helpers import block_signals, path_to_pixmap, set_module_type


class CollapsibleSection(QWidget):
    """A collapsible section with a header and content area."""

    def __init__(self, parent, title, content_widget):
        super().__init__(parent=parent)
        self.parent = parent
        self.content_widget = content_widget
        self.is_expanded = True

        self.layout = CVBoxLayout(self)

        # Header
        self.header_height = 30
        self.header = QWidget()
        self.header.setFixedHeight(self.header_height)
        self.header.setCursor(Qt.PointingHandCursor)
        self.header_layout = CHBoxLayout(self.header)
        self.header_layout.setContentsMargins(5, 5, 5, 5)

        self.toggle_btn = IconButton(
            parent=self.header,
            icon_path=':/resources/icon-expanded.png',
            size=16,
            colorize=True,
        )
        self.toggle_btn.clicked.connect(self.toggle)

        self.title_label = QWidget()
        self.title_label_layout = CHBoxLayout(self.title_label)
        self.label = QLabel(title)
        font = QFont()
        font.setBold(True)
        self.label.setFont(font)
        self.title_label_layout.addWidget(self.label)
        self.title_label_layout.addStretch(1)

        self.header_layout.addWidget(self.toggle_btn)
        self.header_layout.addWidget(self.title_label, 1)

        # Content container
        self.content_container = QWidget()
        self.content_layout = CVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(0, 2, 0, 2)
        self.content_layout.addWidget(content_widget)

        self.layout.addWidget(self.header)
        self.layout.addWidget(self.content_container)

        # Make header clickable
        self.header.mousePressEvent = lambda e: self.toggle()

    def toggle(self):
        """Toggle the expanded/collapsed state."""
        self.is_expanded = not self.is_expanded
        self.content_container.setVisible(self.is_expanded)
        icon_path = ':/resources/icon-expanded.png' if self.is_expanded else ':/resources/icon-collapsed.png'
        pixmap = path_to_pixmap(icon_path, diameter=16)
        self.toggle_btn.setIconPixmap(pixmap)

        # Let splitter redistribute space
        if self.is_expanded:
            self.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
        else:
            self.setMaximumHeight(self.header_height)

    def set_expanded(self, expanded):
        """Set the expanded state."""
        if self.is_expanded != expanded:
            self.toggle()


@set_module_type('Widgets')
class ConfigSideTabs(ConfigWidget):
    """A vertical collection of collapsible, resizable configuration sections.

    Similar to ConfigTabs but displays all sections vertically with
    collapsible headers instead of horizontal tabs. Sections are resizable
    via splitter handles, and collapsed sections redistribute space to others.

    Parameters
    ----------
    parent : QWidget
        The parent widget.
    pages : dict
        Dictionary mapping section names to their content widgets.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        self.layout = CVBoxLayout(self)
        self.pages = kwargs.get('pages', {})
        self.sections = {}

        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.layout.addWidget(self.splitter)
        # self.layout.addStretch(1)

    @override
    def build_schema(self):
        """Build the collapsible sections from `self.pages`."""
        # Clear existing sections
        while self.splitter.count() > 0:
            widget = self.splitter.widget(0)
            widget.setParent(None)
        self.sections.clear()

        # Build all sections
        with block_signals(self):
            for page_name, page_widget in self.pages.items():
                if hasattr(page_widget, 'build_schema'):
                    page_widget.build_schema()

                section = CollapsibleSection(
                    parent=self,
                    title=page_name,
                    content_widget=page_widget,
                )
                self.sections[page_name] = section
                self.splitter.addWidget(section)

        if hasattr(self, 'after_init'):
            self.after_init()

    @override
    def load(self):
        """Load all visible sections."""
        for page_name, section in self.sections.items():
            if section.is_expanded and hasattr(section.content_widget, 'load'):
                section.content_widget.load()

    @override
    def load_config(self, json_config=None):
        """Load configuration into all sections."""
        super().load_config(json_config)

        for page_name, page_widget in self.pages.items():
            if not getattr(page_widget, 'propagate_config', True):
                continue
            if hasattr(page_widget, 'load_config'):
                page_widget.load_config()

    @override
    def get_config(self):
        """Get combined configuration from all sections."""
        config = {}
        for page_name, page_widget in self.pages.items():
            if not getattr(page_widget, 'propagate_config', True):
                continue
            if not hasattr(page_widget, 'get_config'):
                continue

            page_config = page_widget.get_config()
            config.update(page_config)

        return config

    def expand_all(self):
        """Expand all sections."""
        for section in self.sections.values():
            section.set_expanded(True)

    def collapse_all(self):
        """Collapse all sections."""
        for section in self.sections.values():
            section.set_expanded(False)

    def set_section_expanded(self, section_name, expanded):
        """Set the expanded state of a specific section."""
        if section_name in self.sections:
            self.sections[section_name].set_expanded(expanded)