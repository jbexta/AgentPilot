import json
from abc import abstractmethod
from PySide6.QtCore import QTimer
from PySide6.QtGui import Qt
from PySide6.QtWidgets import QWidget, QSizePolicy, QSplitter, QHeaderView, QLineEdit

from gui import system
from gui.gui_utils.helpers import save_table_config
from gui.gui_utils.filter_widget import FilterWidget
from gui.gui_utils.layouts import CVBoxLayout
from gui.gui_utils.tree_buttons import TreeButtons
from gui.widgets.config_fields import ConfigFields

from gui.widgets.config_widget import ConfigWidget
from utils import sql
from utils.helpers import format_llm_tools, readable_class_name


class ConfigTree(ConfigWidget):
    """Base class for a tree widget"""
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        from gui.gui_utils.base_tree_widget import BaseTreeWidget
        self.conf_namespace = kwargs.get('conf_namespace', None)
        self.schema = kwargs.get('schema', [])
        self.layout_type = kwargs.get('layout_type', 'vertical')
        self.resize_inversion = kwargs.get('resize_inversion', False)
        tree_height = kwargs.get('tree_height', None)
        self.readonly = kwargs.get('readonly', False)
        self.filterable = kwargs.get('filterable', False)
        self.searchable = kwargs.get('searchable', False)
        self.dynamic_load = kwargs.get('dynamic_load', False)
        self.folders_groupable = kwargs.get('folders_groupable', False)
        # self.async_load = kwargs.get('async_load', False)
        self.default_item_icon = kwargs.get('default_item_icon', None)
        tree_header_hidden = kwargs.get('tree_header_hidden', False)
        tree_header_resizable = kwargs.get('tree_header_resizable', True)
        self.config_widget = kwargs.get('config_widget', None)
        self.folder_key = kwargs.get('folder_key', None)
        self.folder_config_widget = kwargs.get('folder_config_widget', None)  # self.Folder_Config_Widget(parent=self))
        self.support_item_nesting = kwargs.get('support_item_nesting', False)
        self.group_by_kind = kwargs.get('group_by_kind', False)
        # Maps a `kind` value to the `folders.type` namespace its folders live
        # in, so kind groups can show (and receive) folders as well as items.
        self.kind_folder_key = kwargs.get('kind_folder_key', None)
        self.has_chat = kwargs.get('has_chat', False)

        # patch the update_config method for the folder config widget
        if self.folder_config_widget is not None:
            self.folder_config_widget.hide()
            self.folder_config_widget.setEnabled(False)
            self.folder_config_widget.propagate_config = False
            # self.folder_config_widget.save_config = self.save_folder_config

        self.show_tree_buttons = kwargs.get('show_tree_buttons', True)
        extra_buttons = kwargs.get('extra_buttons', [])

        self.add_item_options = kwargs.get('add_item_options', None)
        self.del_item_options = kwargs.get('del_item_options', None)

        if not self.add_item_options:
            self.add_item_options = {'title': 'Add Item', 'prompt': 'Enter a name for the item:'}
        if not self.del_item_options:
            self.del_item_options = {'title': 'Delete Item', 'prompt': 'Are you sure you want to delete this item?'}

        self.layout = CVBoxLayout(self)
        self.config_layout = None

        self.tree_container = QWidget()
        self.tree_layout = CVBoxLayout(self.tree_container)
        if self.filterable:
            self.filter_widget = FilterWidget(parent=self, **kwargs)
            self.tree_layout.addWidget(self.filter_widget)

        if self.show_tree_buttons:
            self.tree_buttons = TreeButtons(parent=self, extra_buttons=extra_buttons)
            self.tree_layout.addWidget(self.tree_buttons)

        self.search_action = None
        if self.searchable and self.show_tree_buttons:
            self.search_box = QLineEdit()
            self.search_box.setPlaceholderText('Search...')
            self.search_box.textChanged.connect(lambda: self.load())
            self.search_action = self.tree_buttons.inner_widget.addWidget(self.search_box)
            self.search_action.setVisible(False)

        tree_class = kwargs.get('tree_class', BaseTreeWidget)
        self.tree = tree_class(parent=self)
        self.tree.setHeaderHidden(tree_header_hidden)
        self.tree.setSortingEnabled(False)
        self.tree.itemChanged.connect(self.on_cell_edited)
        self.tree.itemSelectionChanged.connect(self.on_item_selected)
        self.tree.itemSelectionChanged.connect(self.defer_update_page_map)
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

        if self.config_widget is not None or self.folder_config_widget is not None:
            splitter_orientation = Qt.Horizontal if self.layout_type == 'horizontal' else Qt.Vertical
            self.splitter = QSplitter(splitter_orientation)
            self.splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.splitter.setChildrenCollapsible(False)
            self.splitter.addWidget(self.tree_container)

            config_container = QWidget()
            self.config_layout = CVBoxLayout(config_container)
            if isinstance(self.config_widget, QWidget):  # self.config_widget:
                self.config_layout.addWidget(self.config_widget)
            if isinstance(self.folder_config_widget, QWidget):  # self.folder_config_widget:
                self.config_layout.addWidget(self.folder_config_widget)

            self.splitter.addWidget(config_container)
            self.layout.addWidget(self.splitter)

            if kwargs.get('collapsible_tree', False):
                self.splitter.setCollapsible(0, True)
                self.splitter.splitterMoved.connect(self.on_tree_splitter_moved)
                if system.manager.config.get(self.tree_collapsed_key, False):
                    self.splitter.setSizes([0, 1])
        else:
            self.layout.addWidget(self.tree_container)
    
    # def set_config_widget(self, config_widget):  # todo temp helper
    #     if self.config_widget is not None:
    #         self.config_layout.removeWidget(self.config_widget)
    #         self.config_widget.deleteLater()
    #     self.config_widget = config_widget
    #     self.config_layout.insertWidget(0, self.config_widget)
    #     self.config_widget.build_schema()

    @property
    def tree_collapsed_key(self):
        return f'ui.tree_collapsed.{type(self).__name__}'

    def on_tree_splitter_moved(self):
        collapsed = self.splitter.sizes()[0] == 0
        if collapsed != system.manager.config.get(self.tree_collapsed_key, False):
            system.manager.config[self.tree_collapsed_key] = collapsed


    @abstractmethod
    def load(self):
        pass

    def get_agent_visualisation(self, refs):
        from textwrap import indent
        lines = [f'{readable_class_name(self)}:']
        tools = self.agent_tools(refs)
        if tools:
            lines.append(indent(tools, '    '))
        active_panel = next(
            (w for w in (self.config_widget, self.folder_config_widget)
             if w is not None and not w.isHidden()),
            None,
        )
        panel_text = active_panel.get_agent_visualisation(refs) if active_panel else ''
        columns = [
            c for c in range(self.tree.columnCount())
            if not self.tree.isColumnHidden(c)
        ]

        def walk(item, depth):
            nonlocal panel_text
            if item.isHidden():
                return
            text = ' | '.join(item.text(c) for c in columns if item.text(c))
            prefix = '    ' * depth
            slash = '/' if item.data(0, Qt.UserRole) == 'folder' else ''
            current = ' (current)' if item.isSelected() else ''
            lines.append(f'{prefix}- {text}{slash}{self.agent_item_suffix(item)}{current}')
            if current and panel_text:
                lines.append(indent(panel_text, prefix + '    '))
                panel_text = ''
            if item.isExpanded():
                walk_children(item, depth + 1)

        def walk_children(parent, depth):
            current = None
            for i in range(parent.childCount()):
                child = parent.child(i)
                if child.isSelected():
                    current = child
                    continue
                walk(child, depth)
            if current:
                walk(current, depth)

        if self.tree.topLevelItemCount():
            lines.append('    Items:')
            walk_children(self.tree.invisibleRootItem(), 2)
        if panel_text:
            lines.append(indent(panel_text, '    '))
        return '\n'.join(lines)

    def agent_tools(self, refs):
        return format_llm_tools(self, refs)

    def agent_item_suffix(self, item):
        return ''

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
    
    def add_folder(self, name=None, parent_folder=None):
        pass

    def add_item(self):
        pass

    def delete_item(self):
        pass

    def rename_item(self):
        pass

    def toggle_search(self, checked):
        self.search_action.setVisible(checked)
        if checked:
            self.search_box.setFocus()
        if self.search_box.text():
            self.load()

    def get_search_text(self):
        if not self.search_action or not self.search_action.isVisible():
            return ''
        return self.search_box.text()

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
                        'default': '',
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