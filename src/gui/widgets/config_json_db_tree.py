from PySide6.QtWidgets import *
from PySide6.QtGui import Qt, QIcon, QPixmap
from typing_extensions import override

from gui.util import TreeButtons, get_field_widget
from utils.helpers import block_signals, convert_to_safe_case
from utils import sql

from gui.widgets.config_widget import ConfigWidget


class ConfigJsonDBTree(ConfigWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)  # , **kwargs)
        from gui.util import BaseTreeWidget, colorize_pixmap
        self.table_name = kwargs.get('table_name', None)
        self.item_icon_path = kwargs.get('item_icon_path', None)
        self.key_field = kwargs.get('key_field', 'id')
        self.show_fields = kwargs.get('show_fields', None)
        self.item_icon = colorize_pixmap(QPixmap(self.item_icon_path))

        self.schema = kwargs.get('schema', [])
        tree_height = kwargs.get('tree_height', None)

        self.readonly = kwargs.get('readonly', False)
        tree_width = kwargs.get('tree_width', 200)
        tree_header_hidden = kwargs.get('tree_header_hidden', False)
        layout_type = kwargs.get('layout_type', 'vertical')

        self.layout = QVBoxLayout(self) if layout_type == 'vertical' else QHBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        tree_layout = QVBoxLayout()
        self.tree_buttons = TreeButtons(parent=self)
        self.tree_buttons.btn_add.clicked.connect(self.add_item)
        self.tree_buttons.btn_del.clicked.connect(self.delete_item)

        self.tree = BaseTreeWidget(parent=self)
        if tree_height:
            self.tree.setFixedHeight(tree_height)
        # self.tree.itemDoubleClicked.connect(self.goto_link)
        self.tree.setHeaderHidden(tree_header_hidden)
        self.tree.setSortingEnabled(False)

        tree_layout.addWidget(self.tree_buttons)
        tree_layout.addWidget(self.tree)
        self.layout.addLayout(tree_layout)

        self.tree.move(-15, 0)

    @override
    def load(self):
        with block_signals(self.tree):
            self.tree.clear()

            id_list = next(iter(self.config.values()), None)
            if id_list is None:
                return
            # id_list = json.loads(row_data_json_str)

            if len(id_list) == 0:
                return
            if not self.show_fields:
                return

            if self.key_field == 'id':
                id_list = [int(i) for i in id_list]
            results = sql.get_results(f"""
                SELECT
                    {','.join(self.show_fields)}
                FROM {self.table_name}
                WHERE {self.key_field} IN ({','.join(['?' for i in id_list])})
            """, id_list)
            for row_tuple in results:
                self.add_new_entry(row_tuple, self.item_icon)

    def add_new_entry(self, row_tuple, icon=None):
        # pass
        # from gui.util import InputSourceComboBox, InputTargetComboBox, BaseComboBox, colorize_pixmap
        with block_signals(self.tree):
            item = QTreeWidgetItem(self.tree, [str(v) for v in row_tuple])

            if self.readonly:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            else:
                item.setFlags(item.flags() | Qt.ItemIsEditable)

            for i, col_schema in enumerate(self.schema):
                column_type = col_schema.get('type', None)
                key = convert_to_safe_case(col_schema.get('key', col_schema['text']))
                # default = col_schema.get('default', '')
                # val = row_tuple[i]

                if column_type != 'text' and column_type != str:
                    widget = get_field_widget(col_schema, parent=self)
                    if not widget:
                        param_type = col_schema.get('type', 'text')
                        print(f'Widget type {param_type} not found in modules. Skipping field: {key}')
                        continue

                    self.tree.setItemWidget(item, i, widget)
                # print('TODO: ADD FIELD')
                # if ftype == 'combo':
                #     pass
                #     # widget = RoleComboBox()
                #     # widget.setFixedWidth(100)
                #     # index = widget.findData(val)
                #     # widget.setCurrentIndex(index)
                #     # widget.currentIndexChanged.connect(self.on_cell_edited)
                #     # self.tree.setItemWidget(item, i, widget)
                # elif ftype == bool:
                #     widget = QCheckBox()
                #     self.tree.setItemWidget(item, i, widget)
                #     widget.setChecked(val)
                #     widget.stateChanged.connect(self.on_cell_edited)
                # elif isinstance(ftype, tuple):
                #     widget = BaseComboBox()
                #     widget.addItems(ftype)
                #     widget.setCurrentText(str(val))
                #
                #     widget.currentIndexChanged.connect(self.on_cell_edited)
                #     self.tree.setItemWidget(item, i, widget)

            if icon:
                item.setIcon(0, QIcon(icon))

    def add_item(self, column_vals=None, icon=None):
        if self.table_name == 'tools':
            list_type = 'TOOL'
        elif self.table_name == 'blocks':
            list_type = 'BLOCK'
        elif self.table_name == 'entities':
            list_type = 'AGENT'
        elif self.table_name == 'modules':
            list_type = 'MODULE'
        else:
            raise NotImplementedError(f'DB table not supported: {self.table_name}')

        from gui.util import TreeDialog
        list_dialog = TreeDialog(
            parent=self,
            title=f'Choose {list_type.capitalize()}',
            list_type=list_type,
            callback=self.add_item_callback,
            # multi_select=True,
        )
        list_dialog.open()

    def add_item_callback(self, item):
        item = item.data(0, Qt.UserRole)
        item_id = item['id']  # is always last column
        item_exists = any([item_id == self.tree.topLevelItem(i).text(len(self.schema) - 1)
                           for i in range(self.tree.topLevelItemCount())])
        if item_exists:
            return

        row_tuple = (item['name'], item['id'])
        self.add_new_entry(row_tuple, self.item_icon)
        self.update_config()

    def delete_item(self):
        item = self.tree.currentItem()
        if item is None:
            return

        self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))
        self.update_config()

    @override
    def update_config(self):
        schema = self.schema
        config = []
        for i in range(self.tree.topLevelItemCount()):
            row_item = self.tree.topLevelItem(i)
            id_index = len(schema) - 1  # always last column
            row_id = row_item.text(id_index)
            config.append(row_id)

        ns = f'{self.conf_namespace}.' if self.conf_namespace else ''
        self.config = {f'{ns}data': config}  # this is instead of calling load_config()
        super().update_config()

    # def goto_link(self, item):  # todo dupe code
    #     from gui.util import find_main_widget
    #     tool_id = item.text(1)
    #     tool_name = item.text(0)
    #     main = find_main_widget(self)
    #     table_name_map = {
    #         'tools': 'Tools',
    #         'blocks': 'Blocks',
    #         'entities': 'Agents',
    #         'modules': 'Modules',
    #     }
    #     page_name = table_name_map[self.table_name]
    #     main.main_menu.settings_sidebar.page_buttons[page_name].click()
    #     # main.main_menu.settings_sidebar.page_buttons['Settings'].click()
    #     # main.page_settings.settings_sidebar.page_buttons['Tools'].click()
    #     tools_tree = main.main_menu.pages[page_name].tree
    #
    #     # for i in range(tools_tree.topLevelItemCount()):
    #     #     row_name = tools_tree.topLevelItem(i).text(0)
    #     #     if row_name == tool_name:
    #     #         tools_tree.setCurrentItem(tools_tree.topLevelItem(i))
    #
    #     # # RECURSIVELY ITERATE ITEMS AND CHILDREN
    #     # def find_item(tree, name):
    #     #     for i in range(tree.topLevelItemCount()):
    #     #         row_name = tree.topLevelItem(i).text(0)
    #     #         if row_name == name:
    #     #             tree.setCurrentItem(tree.topLevelItem(i))
    #     #             return
    #     #         find_item(tree.topLevelItem(i), name)
    #     #
    #     # find_item(tools_tree, tool_name)
    #     # AttributeError: 'PySide6.QtWidgets.QTreeWidgetItem' object has no attribute 'topLevelItemCount'
    #
    #     #fixed here:
    #     for i in range(tools_tree.topLevelItemCount()):
    #         row_name = tools_tree.topLevelItem(i).text(0)
    #         if row_name == tool_name:
    #             tools_tree.setCurrentItem(tools_tree.topLevelItem(i))
    #             break
