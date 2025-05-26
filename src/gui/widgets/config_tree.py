from abc import abstractmethod
from PySide6.QtGui import Qt
from PySide6.QtWidgets import QWidget, QSizePolicy, QSplitter, QHeaderView
from src.gui.util import FilterWidget, CVBoxLayout, TreeButtons

from src.gui.widgets.config_widget import ConfigWidget


class ConfigTree(ConfigWidget):
    """Base class for a tree widget"""
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        from src.gui.util import BaseTreeWidget
        self.conf_namespace = kwargs.get('conf_namespace', None)
        self.schema = kwargs.get('schema', [])
        layout_type = kwargs.get('layout_type', 'vertical')
        tree_height = kwargs.get('tree_height', None)
        self.readonly = kwargs.get('readonly', False)
        self.filterable = kwargs.get('filterable', False)
        self.searchable = kwargs.get('searchable', False)
        self.versionable = kwargs.get('versionable', False)
        self.dynamic_load = kwargs.get('dynamic_load', False)
        self.folders_groupable = kwargs.get('folders_groupable', False)
        # self.async_load = kwargs.get('async_load', False)
        self.default_item_icon = kwargs.get('default_item_icon', None)
        tree_header_hidden = kwargs.get('tree_header_hidden', False)
        tree_header_resizable = kwargs.get('tree_header_resizable', True)
        self.config_widget = kwargs.get('config_widget', None)
        self.folder_key = kwargs.get('folder_key', None)

        self.show_tree_buttons = kwargs.get('show_tree_buttons', True)

        self.add_item_options = kwargs.get('add_item_options', None)
        self.del_item_options = kwargs.get('del_item_options', None)

        self.layout = CVBoxLayout(self)

        splitter_orientation = Qt.Horizontal if layout_type == 'horizontal' else Qt.Vertical
        self.splitter = QSplitter(splitter_orientation)
        self.splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.splitter.setChildrenCollapsible(False)

        self.tree_container = QWidget()
        self.tree_layout = CVBoxLayout(self.tree_container)
        if self.filterable:
            self.filter_widget = FilterWidget(parent=self, **kwargs)
            self.filter_widget.hide()
            self.tree_layout.addWidget(self.filter_widget)

        if self.show_tree_buttons:
            self.tree_buttons = TreeButtons(parent=self, **kwargs)
            self.tree_layout.addWidget(self.tree_buttons)

        self.tree = BaseTreeWidget(parent=self)
        self.tree.setHeaderHidden(tree_header_hidden)
        self.tree.setSortingEnabled(False)
        self.tree.itemChanged.connect(self.on_cell_edited)
        self.tree.itemSelectionChanged.connect(self.on_item_selected)
        self.tree.itemExpanded.connect(self.on_folder_toggled)
        self.tree.itemCollapsed.connect(self.on_folder_toggled)

        if not tree_header_resizable:
            self.tree.header().setSectionResizeMode(QHeaderView.Fixed)

        if tree_height:
            self.tree.setFixedHeight(tree_height)
        self.tree.move(-15, 0)

        # self.fetched_rows_signal.connect(self.load_rows, Qt.QueuedConnection)

        if self.dynamic_load:
            self.tree.verticalScrollBar().valueChanged.connect(self.check_infinite_load)
            self.load_count = 0

        self.tree_layout.addWidget(self.tree)
        self.splitter.addWidget(self.tree_container)

        if self.config_widget:
            self.splitter.addWidget(self.config_widget)

        self.layout.addWidget(self.splitter)

    @abstractmethod
    def load(self):
        pass

    def check_infinite_load(self, item):
        pass

    def on_cell_edited(self, item):
        pass

    def on_item_selected(self):
        pass

    def on_folder_toggled(self, item):
        pass

    def add_item(self):
        pass

    def delete_item(self):
        pass

    def rename_item(self):
        pass