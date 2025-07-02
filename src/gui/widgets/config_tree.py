import json
from abc import abstractmethod
from PySide6.QtGui import Qt
from PySide6.QtWidgets import QWidget, QSizePolicy, QSplitter, QHeaderView
from matplotlib.cbook import silent_list

from gui.util import FilterWidget, CVBoxLayout, TreeButtons, save_table_config
from gui.widgets.config_fields import ConfigFields

from gui.widgets.config_widget import ConfigWidget
from utils import sql


class ConfigTree(ConfigWidget):
    """Base class for a tree widget"""
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        from gui.util import BaseTreeWidget
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
        self.folder_config_widget = kwargs.get('folder_config_widget', self.Folder_Config_Widget(parent=self))

        # patch the update_config method for the folder config widget
        if self.folder_config_widget is not None:
            self.folder_config_widget.hide()
            self.folder_config_widget.setEnabled(False)
            self.folder_config_widget.propagate = False
            # self.folder_config_widget.save_config = self.save_folder_config

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

        if self.config_widget is not None or self.folder_config_widget is not None:
            config_container = QWidget()
            config_layout = CVBoxLayout(config_container)
            if self.config_widget:
                config_layout.addWidget(self.config_widget)
            if self.folder_config_widget:
                config_layout.addWidget(self.folder_config_widget)

            self.splitter.addWidget(config_container)

        self.layout.addWidget(self.splitter)

    @abstractmethod
    def load(self):
        pass

    def check_infinite_load(self, item):
        pass

    def on_edited(self, item):
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

    # def save_folder_config(self):
    #     folder_id = self.tree.get_selected_folder_id()
    #     if folder_id is None:
    #         return
    #     folder_config = self.folder_config_widget.get_config()
    #     save_table_config(
    #         table_name='folders',
    #         item_id=folder_id,
    #         value=json.dumps(folder_config),
    #         ref_widget=self.folder_config_widget,
    #     )

    class Folder_Config_Widget(ConfigFields):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                schema=[
                    {
                        'text': 'Avatar',
                        'key': 'icon_path',
                        'type': 'image',
                        'diameter': 30,
                        'circular': False,
                        'border': False,
                        'default': ':/resources/icon-folder.png',
                        'label_position': None,
                        'row_key': 0,
                    },
                    {
                        'text': 'Name',
                        'type': str,
                        'default': 'Folder',
                        'stretch_x': True,
                        'text_size': 14,
                        # 'text_alignment': Qt.AlignCenter,
                        'label_position': None,
                        'transparent': True,
                        'row_key': 0,
                    },
                    {
                        'text': 'Load to path',
                        'type': str,
                        'default': 'src.members',
                        'text_size': 11,
                        'width': 140,
                        'visibility_predicate': lambda fields: fields.parent.__class__.__name__ == 'Page_Module_Settings',
                        # 'stretch_x': True,
                        # 'text_alignment': Qt.AlignCenter,
                        # 'label_position': 'top',
                        # 'transparent': True,
                        'row_key': 0,
                    },
                    {
                        'text': 'Description',
                        'type': str,
                        'default': '',
                        'num_lines': 10,
                        'stretch_x': True,
                        'stretch_y': True,
                        'transparent': True,
                        'placeholder_text': 'Description',
                        'gen_block_folder_name': 'todo',
                        'label_position': None,
                    },
                ]
            )
            # self.data_source = {
            #     'table_name': 'folders',
            # }

        def save_config(self):
            # item_id = self.get_selected_item_id()
            # config = self.get_config()
            folder_id = self.parent.tree.get_selected_folder_id()
            if folder_id is None:
                return
            config = self.get_config()

            name = config.get('name', 'Folder')
            existing_names = sql.get_results(  # where name like  f'{name}%' and id != {item_id}
                f"SELECT name FROM `folders` WHERE name LIKE ? AND id != ?",
                (f'{name}%', folder_id,), return_type='list'
            )
            # append _n until name not in existing_names
            row_name = name
            n = 0
            while row_name in existing_names:
                n += 1
                row_name = f"{name}_{n}"

            sql.execute(f"""
                UPDATE `folders`
                SET name = ?
                WHERE id = ?
            """, (row_name, folder_id,))

            save_table_config(
                ref_widget=self,
                table_name='folders',
                item_id=folder_id,
                value=json.dumps(config),
            )
            # self.data_source['item_id'] = self.parent.get_selected_folder_id()
            # super().save_config()

        def on_edited(self):
            # if hasattr(self.parent, 'reload_current_row'):
            selected_id = self.parent.get_selected_folder_id()
            self.parent.load(select_folder_id=selected_id)