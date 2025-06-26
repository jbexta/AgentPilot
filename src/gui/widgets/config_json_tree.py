
from PySide6.QtWidgets import *
from PySide6.QtGui import Qt, QIcon, QPixmap
from typing_extensions import override

from src.gui.util import colorize_pixmap, get_field_widget, set_widget_value
from src.utils.helpers import block_signals, display_message_box, convert_to_safe_case, try_parse_json, display_message

from src.gui.widgets.config_tree import ConfigTree


class ConfigJsonTree(ConfigTree):
    """
    A tree widget that is loaded from and saved to a config
    """
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent, **kwargs)

        self.tree_buttons.btn_add.clicked.connect(self.add_item)
        self.tree_buttons.btn_del.clicked.connect(self.delete_item)

    @override
    def load(self):
        with block_signals(self):
            self.tree.clear()

            ns = f'{self.conf_namespace}.' if self.conf_namespace else ''
            row_data_json = self.config.get(f'{ns}data', None)
            if row_data_json is None:
                return

            if isinstance(row_data_json, str):
                parsed, row_data_json = try_parse_json(row_data_json)
                if not parsed:
                    display_message(
                        self,
                        message=f'Error parsing JSON data: {row_data_json}',
                        icon=QMessageBox.Warning,
                    )

            data = row_data_json
            for row_dict in data:
                self.add_new_entry(row_dict)
            self.set_height()

    # @override
    # def update_config(self):
    #     schema = self.schema
    #     config = []
    #     for i in range(self.tree.topLevelItemCount()):
    #         row_item = self.tree.topLevelItem(i)
    #         item_config = {}
    #         for j in range(len(schema)):
    #             key = convert_to_safe_case(schema[j].get('key', schema[j]['text']))
    #             col_type = schema[j].get('type', str)
    #             cell_widget = self.tree.itemWidget(row_item, j)
    #
    #             combos = ['combo', 'input_source', 'input_target']
    #             if col_type in combos:
    #                 # current_index = cell_widget.currentIndex()
    #                 item_data = cell_widget.currentData()
    #                 item_config[key] = item_data
    #                 if col_type == 'input_source':
    #                     item_config['source_options'] = cell_widget.current_options()
    #                 elif col_type == 'input_target':
    #                     item_config['target_options'] = cell_widget.current_options()
    #                 continue  # todo because of the issue below
    #                 # item_config[key] = get_widget_value(cell_widget)  # cell_widget.currentText()
    #             elif isinstance(col_type, str):
    #                 if isinstance(cell_widget, QCheckBox):
    #                     col_type = bool
    #
    #             if col_type == bool:
    #                 item_config[key] = True if cell_widget.checkState() == Qt.Checked else False
    #             elif isinstance(col_type, tuple):
    #                 item_config[key] = cell_widget.currentText()
    #             else:
    #                 item_config[key] = row_item.text(j)
    #
    #         tag = row_item.data(0, Qt.UserRole)
    #         if tag == 'folder':
    #             item_config['_TYPE'] = 'folder'
    #         config.append(item_config)
    #
    #     ns = f'{self.conf_namespace}.' if self.conf_namespace else ''
    #     self.config = {f'{ns}data': config}
    #     super().update_config()

    def get_config(self):
        schema = self.schema
        config = []
        for i in range(self.tree.topLevelItemCount()):
            row_item = self.tree.topLevelItem(i)
            item_config = {}
            for j in range(len(schema)):
                key = convert_to_safe_case(schema[j].get('key', schema[j]['text']))
                # col_type = schema[j].get('type', str)
                cell_widget = self.tree.itemWidget(row_item, j)
                if (cell_widget and
                        not isinstance(cell_widget, QTextEdit) and
                        not isinstance(cell_widget, QLineEdit) and
                        hasattr(cell_widget, 'get_value')):  # todo
                    item_config[key] = cell_widget.get_value()
                else:
                    item_config[key] = row_item.text(j)

                # combos = ['combo', 'input_source', 'input_target']
                # if col_type in combos:
                #     # current_index = cell_widget.currentIndex()
                #     item_data = cell_widget.currentData()
                #     item_config[key] = item_data
                #     if col_type == 'input_source':
                #         item_config['source_options'] = cell_widget.current_options()
                #     elif col_type == 'input_target':
                #         item_config['target_options'] = cell_widget.current_options()
                #     continue  # todo because of the issue below
                #     # item_config[key] = get_widget_value(cell_widget)  # cell_widget.currentText()
                # elif isinstance(col_type, str):
                #     if isinstance(cell_widget, QCheckBox):
                #         col_type = bool
                #
                # if col_type == bool:
                #     item_config[key] = True if cell_widget.checkState() == Qt.Checked else False
                # elif isinstance(col_type, tuple):
                #     item_config[key] = cell_widget.currentText()
                # else:
                #     item_config[key] = row_item.text(j)

            tag = row_item.data(0, Qt.UserRole)
            if tag == 'folder':
                item_config['_TYPE'] = 'folder'
            config.append(item_config)

        ns = f'{self.conf_namespace}.' if self.conf_namespace else ''
        return {f'{ns}data': config}

    def add_new_entry(self, row_dict, parent_item=None, icon=None):
        # from src.gui.util import RoleComboBox, InputSourceComboBox, InputTargetComboBox, BaseComboBox, colorize_pixmap
        with block_signals(self.tree):
            col_values = [row_dict.get(convert_to_safe_case(col_schema.get('key', col_schema['text'])), None)
                          for col_schema in self.schema]

            parent_item = parent_item or self.tree
            item = QTreeWidgetItem(parent_item, [str(v) for v in col_values])

            if self.readonly:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            else:
                item.setFlags(item.flags() | Qt.ItemIsEditable)

            # combos = ['RoleComboBox', 'InputSourceComboBox', 'InputTargetComboBox']
            for i, col_schema in enumerate(self.schema):
                column_type = col_schema.get('type', None)
                default = col_schema.get('default', '')
                key = convert_to_safe_case(col_schema.get('key', col_schema['text']))
                val = row_dict.get(key, default)
                # print('TODO 2: ADD FIELD')

                if column_type != 'text' and column_type != str:
                    widget = get_field_widget(col_schema, parent=self)
                    if not widget:
                        param_type = col_schema.get('type', 'text')
                        print(f'Widget type {param_type} not found in modules. Skipping field: {key}')
                        continue

                    self.tree.setItemWidget(item, i, widget)
                    if val and hasattr(widget, 'set_value'):
                        widget.set_value(val)
                        # set_widget_value(widget, val)

                # if ftype in combos:
                #     if ftype == 'RoleComboBox':
                #         widget = RoleComboBox()
                #     elif ftype == 'InputSourceComboBox':
                #         widget = InputSourceComboBox(self)
                #     elif ftype == 'InputTargetComboBox':
                #         widget = InputTargetComboBox(self)
                #
                #     # elif val:
                #     #     widget.setCurrentText(val)
                #     #     widget.customCurrentIndexChanged.connect(self.cell_edited)
                #     self.tree.setItemWidget(item, i, widget)
                #
                #     # index = widget.findData(val)
                #     # widget.setCurrentIndex(index)
                #     # set the tree item combo widget instead
                #     widget = self.tree.itemWidget(item, i)
                #     index = widget.findData(val)
                #     widget.setCurrentIndex(index)
                #
                #     if ftype == 'InputSourceComboBox':
                #         widget.set_options(val, row_dict.get('source_options', None))
                #
                #     # if ftype == 'RoleComboBox':
                #     widget.currentIndexChanged.connect(self.on_cell_edited)
                #     # else:
                #     #     widget.main_combo.currentIndexChanged.connect(self.cell_edited)
                #
                # elif ftype == QPushButton:
                #     btn_func = col_schema.get('func', None)
                #     btn_partial = partial(btn_func, row_dict)
                #     btn_icon_path = col_schema.get('icon', '')
                #     pixmap = colorize_pixmap(QPixmap(btn_icon_path))
                #     self.tree.setItemIconButtonColumn(item, i, pixmap, btn_partial)
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

            is_folder = row_dict.get('_TYPE', None) == 'folder'
            if is_folder:
                item.setData(0, Qt.UserRole, 'folder')
                item.setIcon(1, QIcon(colorize_pixmap(QPixmap(':/resources/icon-folder.png'))))

                folder_data = row_dict.get('_data', [])
                for row_data in folder_data:
                    self.add_new_entry(row_data, parent_item=item)
                # item.setIcon(0, QIcon(':/icons/folder.png'))
            # return item

    def set_height(self):
        # tree height including column header and row height * number of rows
        header_height = self.tree.header().height()
        row_height = self.tree.sizeHintForRow(0)
        row_count = self.tree.topLevelItemCount()
        self.setFixedHeight(header_height + (row_height * row_count) + 40)

    @override
    def on_cell_edited(self, item):
        self.update_config()
        col_indx = self.tree.currentColumn()
        field_schema = self.schema[col_indx]

        on_edit_reload = field_schema.get('on_edit_reload', False)
        if on_edit_reload:
            self.load()

    def add_item(self, row_dict=None, icon=None):
        if row_dict is None:
            row_dict = {convert_to_safe_case(col.get('key', col['text'])): col.get('default', '')
                        for col in self.schema}
        self.add_new_entry(row_dict, icon)
        self.update_config()
        self.set_height()

    def delete_item(self):
        item = self.tree.currentItem()
        if item is None:
            return

        get_columns = ['content', 'description']
        col_indexs = [i for i, col in enumerate(self.schema)
                         if convert_to_safe_case(col.get('key', col['text'])) in get_columns]
        show_warning = False
        for i in col_indexs:
            col_val = item.text(i)
            if col_val:
                show_warning = True

        if show_warning:
            retval = display_message_box(
                icon=QMessageBox.Warning,
                title="Delete item",
                text="Are you sure you want to delete this item?",
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if retval != QMessageBox.Yes:
                return False

        self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))
        self.update_config()
        self.set_height()
