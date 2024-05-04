
import json
import logging
import os
import uuid
from abc import abstractmethod
from functools import partial
from sqlite3 import IntegrityError

from PySide6.QtCore import Signal, QFileInfo
from PySide6.QtWidgets import *
from PySide6.QtGui import QFont, Qt, QIcon, QPixmap, QCursor

# from agent.base import Agent
from src.utils.helpers import block_signals, path_to_pixmap, block_pin_mode, display_messagebox
from src.gui.widgets import BaseComboBox, ModelComboBox, CircularImageLabel, \
    ColorPickerWidget, FontComboBox, BaseTreeWidget, IconButton, colorize_pixmap, LanguageComboBox, RoleComboBox, \
    clear_layout, ListDialog, ToggleButton, HelpIcon, PluginComboBox, SandboxComboBox
from src.utils import sql


class ConfigWidget(QWidget):
    def __init__(self, parent):
        super().__init__(parent=None)
        self.parent = parent
        self.config = {}
        self.schema = []
        self.namespace = None

    @abstractmethod
    def build_schema(self):
        pass

    @abstractmethod
    def load(self):
        pass

    def load_config(self, json_config=None):
        """Loads the config dict from the root config widget"""
        if json_config is not None:
            if isinstance(json_config, str):
                json_config = json.loads(json_config)
            self.config = json_config if json_config else {}
            # self.load()
        else:
            parent_config = getattr(self.parent, 'config', {})  # self.parent.config  # get_config()

            if self.namespace is None and not isinstance(self, ConfigDBTree):  # is not None:
                # raise NotImplementedError('Namespace not implemented')
                self.config = parent_config
            else:
                self.config = {k: v for k, v in parent_config.items() if k.startswith(f'{self.namespace}.')}
            # else:
            #     self.config = parent_config

        if hasattr(self, 'widgets'):
            for widget in self.widgets:
                if hasattr(widget, 'load_config'):
                    widget.load_config()
        elif hasattr(self, 'pages'):
            for _, page in self.pages.items():
                if hasattr(page, 'load_config'):
                    page.load_config()
        elif hasattr(self, 'plugin_config'):
            if self.plugin_config is not None:
                self.plugin_config.load_config()

        # if json_config is not None:  # todo
        #     self.load()

    def get_config(self):
        if isinstance(self, ConfigJsonTree):
            schema = self.schema
            config = []
            for i in range(self.tree.topLevelItemCount()):
                row_item = self.tree.topLevelItem(i)
                item_config = {}
                for j in range(len(schema)):
                    key = schema[j].get('key', schema[j]['text']).replace(' ', '_').lower()
                    col_type = schema[j].get('type', str)
                    if col_type == 'RoleComboBox':
                        cell_widget = self.tree.itemWidget(row_item, j)
                        item_config[key] = cell_widget.currentData()
                    elif col_type == bool:
                        cell_widget = self.tree.itemWidget(row_item, j)
                        item_config[key] = True if cell_widget.checkState() == Qt.Checked else False
                    else:
                        item_config[key] = row_item.text(j)
                config.append(item_config)

            ns = self.namespace if self.namespace else ''
            return {f'{ns}.data': json.dumps(config)}
        # elif isinstance(self, ConfigPlugin):
        #     if self.plugin_config is not None:
        #         return self.plugin_config.get_config()

        config = {}
        if hasattr(self, 'member_type'):
            config['_TYPE'] = self.member_type

        if hasattr(self, 'widgets'):
            for widget in self.widgets:
                if not getattr(widget, 'propagate', True) or not hasattr(widget, 'get_config'):
                    continue
                # if hasattr(widget, 'get_config'):
                config.update(widget.get_config())
            return config
        elif hasattr(self, 'pages'):
            for _, page in self.pages.items():
                if not getattr(page, 'propagate', True) or not hasattr(page, 'get_config'):
                    continue
                page_config = page.get_config()  # getattr(page, 'config', {})
                config.update(page_config)
            return config
        else:
            # return self.get_config()
            return self.config

    def update_config(self):
        """Bubble update config dict to the root config widget"""
        if hasattr(self.parent, 'update_config'):
            self.parent.update_config()

        if hasattr(self, 'save_config'):
            self.save_config()


class ConfigJoined(ConfigWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        layout_type = kwargs.get('layout_type', QVBoxLayout)
        self.layout = layout_type(self)
        self.widgets = kwargs.get('widgets', [])

    def build_schema(self):
        for widget in self.widgets:
            if hasattr(widget, 'build_schema'):
                widget.build_schema()
            self.layout.addWidget(widget)
        self.layout.addStretch(1)

    def load(self):
        for widget in self.widgets:
            if hasattr(widget, 'load'):
                widget.load()


class ConfigFields(ConfigWidget):
    def __init__(self, parent, namespace=None, *args, **kwargs):
        super().__init__(parent=parent)

        self.namespace = namespace
        self.alignment = kwargs.get('alignment', Qt.AlignLeft)
        self.layout = CVBoxLayout(self)
        # self.layout.setAlignment(self.alignment)
        self.label_width = kwargs.get('label_width', None)
        self.label_text_alignment = kwargs.get('label_text_alignment', Qt.AlignLeft)
        self.margin_left = kwargs.get('margin_left', 0)

    def build_schema(self):
        """Build the widgets from the schema list"""
        clear_layout(self.layout)
        schema = self.schema
        if not schema:
            return

        self.layout.setContentsMargins(self.margin_left, 0, 0, 0)
        row_layout = None
        last_row_key = None
        for i, param_dict in enumerate(schema):
            param_text = param_dict['text']
            key = param_dict.get('key', param_text.replace(' ', '_').replace('-', '_').lower())
            row_key = param_dict.get('row_key', None)
            label_position = param_dict.get('label_position', 'left')
            label_width = param_dict.get('label_width', None) or self.label_width
            has_toggle = param_dict.get('has_toggle', False)
            tooltip = param_dict.get('tooltip', None)
            has_edit_button = param_dict.get('has_edit_button', False)

            if row_key is not None and row_layout is None:
                row_layout = CHBoxLayout()
            elif row_key is not None and row_layout is not None and row_key != last_row_key:
                self.layout.addLayout(row_layout)
                row_layout = CHBoxLayout()
            elif row_key is None and row_layout is not None:
                self.layout.addLayout(row_layout)
                row_layout = None

            last_row_key = row_key

            current_value = self.config.get(f'{key}', None)
            if current_value is not None:
                param_dict['default'] = current_value

            widget = self.create_widget(**param_dict)
            setattr(self, key, widget)
            self.connect_signal(widget)

            if hasattr(widget, 'build_schema'):
                widget.build_schema()

            param_layout = CHBoxLayout() if label_position == 'left' else CVBoxLayout()
            param_layout.setContentsMargins(2, 8, 2, 0)
            param_layout.setAlignment(self.alignment)
            if label_position is not None:
                label_layout = CHBoxLayout()
                label_layout.setAlignment(self.label_text_alignment)
                param_label = QLabel(param_text)
                param_label.setAlignment(self.label_text_alignment)
                if label_width:
                    param_label.setFixedWidth(label_width)

                label_layout.addWidget(param_label)

                label_minus_width = 0
                if tooltip:
                    info_label = HelpIcon(parent=self, tooltip=tooltip)
                    info_label.setAlignment(self.label_text_alignment)
                    label_minus_width += 22
                    label_layout.addWidget(info_label)

                if has_toggle:
                    toggle = QCheckBox()
                    toggle.setFixedWidth(20)
                    setattr(self, f'{key}_tgl', toggle)
                    self.connect_signal(toggle)
                    toggle.stateChanged.connect(partial(self.toggle_widget, toggle, key))
                    # toggle.setChecked(param_dict['default'])
                    # toggle.stateChanged.connect(partial(self.update_config, key, toggle))
                    label_minus_width += 20
                    label_layout.addWidget(toggle)

                if has_toggle or tooltip:
                    label_layout.addStretch(1)

                if label_width:
                    param_label.setFixedWidth(label_width - label_minus_width)
                param_layout.addLayout(label_layout)

            param_layout.addWidget(widget)
            param_layout.addStretch(1)

            if row_layout:
                row_layout.addLayout(param_layout)
            else:
                self.layout.addLayout(param_layout)

        if row_layout:
            self.layout.addLayout(row_layout)

        self.layout.addStretch(1)

        if hasattr(self, 'after_init'):
            self.after_init()

    def load(self):
        """Loads the widget values from the config dict"""
        with block_signals(self):
            for param_dict in self.schema:
                param_text = param_dict['text']
                key = param_dict.get('key', param_text.replace(' ', '_').replace('-', '_').lower())

                widget = getattr(self, key)
                config_key = f"{self.namespace}.{key}" if self.namespace else key

                config_value = self.config.get(config_key, None)
                has_config_value = config_value is not None

                toggle = getattr(self, f'{key}_tgl', None)
                if toggle:
                    toggle.setChecked(has_config_value)
                    widget.setVisible(has_config_value)

                if has_config_value:
                    self.set_widget_value(widget, config_value)
                else:
                    self.set_widget_value(widget, param_dict['default'])

    def update_config(self):
        config = {}
        for param_dict in self.schema:
            param_text = param_dict['text']
            param_key = param_dict.get('key', param_text.replace(' ', '_').replace('-', '_').lower())
            config_key = f"{self.namespace}.{param_key}" if self.namespace else param_key

            widget_toggle = getattr(self, f'{param_key}_tgl', None)
            if widget_toggle:
                if not widget_toggle.isChecked():
                    config.pop(config_key, None)
                    continue

            widget = getattr(self, param_key)
            config[config_key] = get_widget_value(widget)

        self.config = config
        super().update_config()

    def create_widget(self, **kwargs):
        param_type = kwargs['type']
        default_value = kwargs['default']
        param_width = kwargs.get('width', None)
        num_lines = kwargs.get('num_lines', 1)
        text_size = kwargs.get('text_size', None)
        text_alignment = kwargs.get('text_alignment', Qt.AlignLeft)
        highlighter = kwargs.get('highlighter', None)
        transparent = kwargs.get('transparent', False)
        minimum = kwargs.get('minimum', 0)
        maximum = kwargs.get('maximum', 1)
        step = kwargs.get('step', 1)

        set_width = param_width or 50
        if param_type == bool:
            widget = QCheckBox()
            widget.setChecked(default_value)
        elif param_type == int:
            widget = QSpinBox()
            widget.setValue(default_value)
            widget.setMinimum(minimum)
            widget.setMaximum(maximum)
            widget.setSingleStep(step)
        elif param_type == float:
            widget = QDoubleSpinBox()
            widget.setValue(default_value)
            widget.setMinimum(minimum)
            widget.setMaximum(maximum)
            widget.setSingleStep(step)
        elif param_type == str:
            widget = QLineEdit() if num_lines == 1 else QTextEdit()

            transparency = 'background-color: transparent;' if transparent else ''
            widget.setStyleSheet(f"border-radius: 6px;" + transparency)
            widget.setAlignment(text_alignment)

            if text_size:
                font = widget.font()
                font.setPointSize(text_size)
                widget.setFont(font)
            if highlighter:
                widget.highlighter = highlighter(widget.document())
            font_metrics = widget.fontMetrics()
            height = (font_metrics.lineSpacing() + 2) * num_lines + widget.contentsMargins().top() + widget.contentsMargins().bottom()
            widget.setFixedHeight(height)
            widget.setText(default_value)
            set_width = param_width or 150
        elif isinstance(param_type, tuple):
            widget = BaseComboBox()
            widget.addItems(param_type)
            widget.setCurrentText(str(default_value))
            set_width = param_width or 150
        elif param_type == 'CircularImageLabel':
            widget = CircularImageLabel()
            widget.setImagePath(str(default_value))
            set_width = widget.width()
        elif param_type == 'ModelComboBox':
            widget = ModelComboBox()
            widget.setCurrentText(str(default_value))
            set_width = param_width or 150
        elif param_type == 'SandboxComboBox':
            widget = SandboxComboBox()
            widget.setCurrentText(str(default_value))
            set_width = param_width or 150
        elif param_type == 'FontComboBox':
            widget = FontComboBox()
            widget.setCurrentText(str(default_value))
            set_width = param_width or 150
        elif param_type == 'RoleComboBox':
            widget = RoleComboBox()
            widget.setCurrentText(str(default_value))
            set_width = param_width or 150
        elif param_type == 'LanguageComboBox':
            widget = LanguageComboBox()
            # widget.setCurrentText(str(default_value))
            set_width = param_width or 150
        elif param_type == 'ColorPickerWidget':
            widget = ColorPickerWidget()
            widget.setColor(str(default_value))
            set_width = param_width or 25
        else:
            raise ValueError(f'Unknown param type: {param_type}')

        if set_width:
            widget.setFixedWidth(set_width)

        return widget

    def connect_signal(self, widget):
        if isinstance(widget, CircularImageLabel):
            widget.avatarChanged.connect(self.update_config)
        elif isinstance(widget, ColorPickerWidget):
            widget.colorChanged.connect(self.update_config)
        elif isinstance(widget, QCheckBox):
            widget.stateChanged.connect(self.update_config)
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(self.update_config)
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(self.update_config)
        elif isinstance(widget, QSpinBox):
            widget.valueChanged.connect(self.update_config)
        elif isinstance(widget, QDoubleSpinBox):
            widget.valueChanged.connect(self.update_config)
        elif isinstance(widget, QTextEdit):
            widget.textChanged.connect(self.update_config)
        else:
            raise Exception(f'Widget not implemented: {type(widget)}')

    def set_widget_value(self, widget, value):
        if isinstance(widget, CircularImageLabel):
            widget.setImagePath(value)
        elif isinstance(widget, ColorPickerWidget):
            widget.setColor(value)
        elif isinstance(widget, ModelComboBox):
            widget.set_key(value)
        elif isinstance(widget, SandboxComboBox):
            widget.set_key(value)
        elif isinstance(widget, QCheckBox):
            widget.setChecked(value)
        elif isinstance(widget, QLineEdit):
            widget.setText(value)
        elif isinstance(widget, QComboBox):
            widget.setCurrentText(str(value))
        elif isinstance(widget, QSpinBox):
            widget.setValue(int(value))
        elif isinstance(widget, QDoubleSpinBox):
            widget.setValue(float(value))
        elif isinstance(widget, QTextEdit):
            widget.setText(value)
        else:
            raise Exception(f'Widget not implemented: {type(widget)}')

    def toggle_widget(self, toggle, key, _):
        widget = getattr(self, key)
        widget.setVisible(toggle.isChecked())

    # def clear_layout(self, layout):
    #     """Clear all layouts and widgets from the given layout"""
    #     while layout.count():
    #         item = layout.takeAt(0)
    #         widget = item.widget()
    #         if widget is not None:
    #             widget.deleteLater()
    #         else:
    #             child_layout = item.layout()
    #             if child_layout is not None:
    #                 self.clear_layout(child_layout)
    #     self.layout.setAlignment(self.alignment)


# class ConfigComboBox(BaseComboBox):
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         pass


class TreeButtonsWidget(QWidget):
    def __init__(self, parent):  # , extra_tree_buttons=None):
        super().__init__(parent=parent)
        self.layout = CHBoxLayout(self)

        self.btn_add = IconButton(
            parent=self,
            icon_path=':/resources/icon-new.png',
            tooltip='Add',
            size=18,
        )
        self.btn_del = IconButton(
            parent=self,
            icon_path=':/resources/icon-minus.png',
            tooltip='Delete',
            size=18,
        )
        self.layout.addWidget(self.btn_add)
        self.layout.addWidget(self.btn_del)

        if getattr(parent, 'folder_key', False):
            self.btn_new_folder = IconButton(
                parent=self,
                icon_path=':/resources/icon-new-folder.png',
                tooltip='New Folder',
                size=18,
            )
            self.layout.addWidget(self.btn_new_folder)

        if getattr(parent, 'filterable', False):
            self.btn_filter = ToggleButton(
                parent=self,
                icon_path=':/resources/icon-filter.png',
                icon_path_checked=':/resources/icon-filter-filled.png',
                tooltip='Filter',
                size=18,
            )
            self.layout.addWidget(self.btn_filter)

        if getattr(parent, 'searchable', False):
            self.btn_search = ToggleButton(
                parent=self,
                icon_path=':/resources/icon-search.png',
                icon_path_checked=':/resources/icon-search-filled.png',
                tooltip='Search',
                size=18,
            )
            self.layout.addWidget(self.btn_search)

        self.layout.addStretch(1)


class ConfigDBTree(ConfigWidget):
    """
    A widget that displays a tree of items from the db, with buttons to add and delete items.
    Can contain a config widget shown either to the right of the tree or below it,
    representing the config for each item in the tree.
    """
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)

        self.schema = kwargs.get('schema', [])
        self.query = kwargs.get('query', None)
        self.query_params = kwargs.get('query_params', None)
        self.db_table = kwargs.get('db_table', None)
        self.propagate = kwargs.get('propagate', True)
        self.db_config_field = kwargs.get('db_config_field', 'config')
        self.add_item_prompt = kwargs.get('add_item_prompt', None)
        self.del_item_prompt = kwargs.get('del_item_prompt', None)
        self.config_widget = kwargs.get('config_widget', None)
        self.has_config_field = kwargs.get('has_config_field', True)  # todo - remove
        self.readonly = kwargs.get('readonly', True)
        self.folder_key = kwargs.get('folder_key', None)
        self.init_select = kwargs.get('init_select', True)
        self.filterable = kwargs.get('filterable', False)
        self.searchable = kwargs.get('searchable', False)
        tree_height = kwargs.get('tree_height', None)
        tree_width = kwargs.get('tree_width', 200)
        tree_header_hidden = kwargs.get('tree_header_hidden', False)
        layout_type = kwargs.get('layout_type', QVBoxLayout)
        # extra_tree_buttons = kwargs.get('extra_tree_buttons', None)

        self.layout = layout_type(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        tree_layout = QVBoxLayout()
        self.tree_buttons = TreeButtonsWidget(parent=self)  # , extra_tree_buttons=extra_tree_buttons)
        self.tree_buttons.btn_add.clicked.connect(self.add_item)
        self.tree_buttons.btn_del.clicked.connect(self.delete_item)
        if hasattr(self.tree_buttons, 'btn_new_folder'):
            self.tree_buttons.btn_new_folder.clicked.connect(self.add_folder)

        self.tree = BaseTreeWidget(parent=self)
        self.tree.setSortingEnabled(False)
        self.tree.setFixedWidth(tree_width)
        if tree_height:
            self.tree.setFixedHeight(tree_height)
        self.tree.itemChanged.connect(self.field_edited)
        self.tree.itemSelectionChanged.connect(self.on_item_selected)
        # self.tree.mouseReleaseEvent.connect(self.mouse_ReleaseEvent)
        self.tree.setHeaderHidden(tree_header_hidden)

        tree_layout.addWidget(self.tree_buttons)
        tree_layout.addWidget(self.tree)
        self.layout.addLayout(tree_layout)
        # move left 5 px
        self.tree.move(-15, 0)

        if not self.add_item_prompt:
            self.tree_buttons.btn_add.hide()
        if not self.del_item_prompt:
            self.tree_buttons.btn_del.hide()

        if self.config_widget:
            self.layout.addWidget(self.config_widget)

    def build_schema(self):
        schema = self.schema
        if not schema:
            return

        self.tree.build_columns_from_schema(schema)

        if self.config_widget:
            self.config_widget.build_schema()

    def load(self, select_id=None):
        """
        Loads the QTreeWidget with folders and agents from the database.
        """
        if not self.query:
            return

        folder_query = """
            SELECT 
                id, 
                name, 
                parent_id, 
                type, 
                ordr 
            FROM folders 
            WHERE `type` = ?
            ORDER BY ordr
        """

        folders_data = sql.get_results(query=folder_query, params=(self.folder_key,))
        data = sql.get_results(query=self.query, params=self.query_params)
        self.tree.load(
            data=data,
            folders_data=folders_data,
            select_id=select_id,
            folder_key=self.folder_key,
            init_select=self.init_select,
            readonly=self.readonly,
            schema=self.schema
        )

    def update_config(self):
        """Overrides to stop propagation to the parent."""
        self.save_config()

    def save_config(self):
        """
        Saves the config to the database using the tree selected ID.
        """
        id = self.get_selected_item_id()
        json_config = json.dumps(self.config_widget.get_config())
        sql.execute(f"""UPDATE `{self.db_table}` 
                        SET `{self.db_config_field}` = ?
                        WHERE id = ?
                    """, (json_config, id,))

    def get_selected_item_id(self):
        return self.tree.get_selected_item_id()

    def get_selected_folder_id(self):
        return self.tree.get_selected_folder_id()

    def get_column_value(self, column):
        item = self.tree.currentItem()
        if not item:
            return None
        return item.text(column)

    def field_edited(self, item):
        id = int(item.text(1))
        col_indx = self.tree.currentColumn()
        col_key = self.schema[col_indx].get('key', None)
        new_value = item.text(col_indx)
        if not col_key:
            return

        sql.execute(f"""
            UPDATE `{self.db_table}`
            SET `{col_key}` = ?
            WHERE id = ?
        """, (new_value, id,))

    def add_item(self):
        dlg_title, dlg_prompt = self.add_item_prompt
        with block_pin_mode():
            text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt)

            if not ok:
                return False

        try:
            # raise NotImplementedError('todo')
            if self.db_table == 'entities':
                kind = 'AGENT'  # self.get_kind() if hasattr(self, 'get_kind') else ''
                agent_config = json.dumps({'info.name': text})
                sql.execute(f"INSERT INTO `entities` (`name`, `kind`, `config`) VALUES (?, ?, ?)",
                            (text, kind, agent_config))
            elif self.db_table == 'models':
                kind = self.get_kind() if hasattr(self, 'get_kind') else ''
                api_id = self.parent.parent.parent.get_selected_item_id()
                sql.execute(f"INSERT INTO `models` (`api_id`, `kind`, `name`) VALUES (?, ?, ?)",
                            (api_id, kind, text,))
            elif self.db_table == 'tools':
                tool_uuid = str(uuid.uuid4())
                sql.execute(f"INSERT INTO `tools` (`name`, `uuid`) VALUES (?, ?)", (text, tool_uuid,))
            else:
                sql.execute(f"INSERT INTO `{self.db_table}` (`name`) VALUES (?)", (text,))

            last_insert_id = sql.get_scalar("SELECT seq FROM sqlite_sequence WHERE name=?", (self.db_table,))
            self.load(select_id=last_insert_id)
            return True

        except IntegrityError:
            display_messagebox(
                icon=QMessageBox.Warning,
                title='Error',
                text='Item already exists',
            )
            return False

    def delete_item(self):
        item = self.tree.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            retval = display_messagebox(
                icon=QMessageBox.Warning,
                title="Delete folder",
                text="Are you sure you want to delete this folder? It's contents will be extracted.",
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if retval != QMessageBox.Yes:
                return False

            folder_id = int(item.text(1))
            folder_parent = item.parent() if item else None
            folder_parent_id = folder_parent.text(1) if folder_parent else None

            # Unpack all items from folder to parent folder (or root)
            sql.execute(f"""
                UPDATE `{self.db_table}`
                SET folder_id = {'NULL' if not folder_parent_id else folder_parent_id}
                WHERE folder_id = ?
            """, (folder_id,))
            # Unpack all folders from folder to parent folder (or root)
            sql.execute(f"""
                UPDATE `folders`
                SET parent_id = {'NULL' if not folder_parent_id else folder_parent_id}
                WHERE parent_id = ?
            """, (folder_id,))

            sql.execute(f"""
                DELETE FROM folders
                WHERE id = ?
            """, (folder_id,))

            self.load()
            return True
        else:
            id = self.get_selected_item_id()
            if not id:
                return False

            raise NotImplementedError('todo')
            if self.db_table == 'agents':
                context_count = sql.get_scalar("""
                    SELECT
                        COUNT(*)
                    FROM contexts_members
                    WHERE agent_id = ?""", (id,))

                if context_count > 0:
                    name = self.get_column_value(0)
                    display_messagebox(
                        icon=QMessageBox.Warning,
                        text=f"Cannot delete '{name}' because it exists in {context_count} contexts.",
                        title="Warning",
                        buttons=QMessageBox.Ok
                    )
                    return False

            dlg_title, dlg_prompt = self.del_item_prompt

            retval = display_messagebox(
                icon=QMessageBox.Warning,
                title=dlg_title,
                text=dlg_prompt,
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if retval != QMessageBox.Yes:
                return False

            try:
                if self.db_table == 'contexts':
                    context_id = id
                    context_member_ids = sql.get_results("SELECT id FROM contexts_members WHERE context_id = ?",
                                                         (context_id,),
                                                         return_type='list')
                    sql.execute("DELETE FROM contexts_members_inputs WHERE member_id IN ({}) OR input_member_id IN ({})".format(
                        ','.join([str(i) for i in context_member_ids]),
                        ','.join([str(i) for i in context_member_ids])
                    ))
                    sql.execute("DELETE FROM contexts_messages WHERE context_id = ?;",
                                (context_id,))  # todo update delete to cascade branches & transaction
                    sql.execute('DELETE FROM contexts_members WHERE context_id = ?', (context_id,))
                    sql.execute("DELETE FROM contexts WHERE id = ?;", (context_id,))

                else:
                    sql.execute(f"DELETE FROM `{self.db_table}` WHERE `id` = ?", (id,))

                self.load()
                return True

            except Exception:
                display_messagebox(
                    icon=QMessageBox.Warning,
                    title='Error',
                    text='Item could not be deleted',
                )
                return False

    def rename_item(self):
        item = self.tree.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            current_name = item.text(0)
            dlg_title, dlg_prompt = ('Rename folder', 'Enter a new name for the folder')
            text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt, text=current_name)
            if not ok:
                return

            sql.execute(f"UPDATE `folders` SET `name` = ? WHERE id = ?",
                        (text, int(item.text(1))))
            self.load()

        else:
            pass

    def on_item_selected(self):
        id = self.get_selected_item_id()
        if not id:
            self.toggle_config_widget(False)
            return

        self.toggle_config_widget(True)

        if self.has_config_field:
            json_config = sql.get_scalar(f"""
                SELECT
                    `{self.db_config_field}`
                FROM `{self.db_table}`
                WHERE id = ?
            """, (id,))
            self.config_widget.load_config(json_config)

        # if hasattr(self.config_widget, 'ref_id'):
        #     self.config_widget.ref_id = id

        if self.config_widget is not None:
            self.config_widget.load()

    def toggle_config_widget(self, enabled):
        if self.config_widget is not None:
            self.config_widget.setEnabled(enabled)
            self.config_widget.setVisible(enabled)

    def add_folder(self):
        item = self.tree.currentItem()
        parent_item = item.parent() if item else None
        parent_id = int(parent_item.text(1)) if parent_item else None

        dlg_title, dlg_prompt = ('New folder', 'Enter the name of the new folder')
        text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt)
        if not ok:
            return

        sql.execute(f"INSERT INTO `folders` (`name`, `parent_id`, `type`) VALUES (?, ?, ?)",
                    (text, parent_id, self.folder_key))
        self.load()

    def show_context_menu(self):
        menu = QMenu(self)

        btn_rename = menu.addAction('Rename')
        btn_delete = menu.addAction('Delete')

        btn_rename.triggered.connect(self.rename_item)
        btn_delete.triggered.connect(self.delete_item)

        menu.exec_(QCursor.pos())


class ConfigJsonTree(ConfigWidget):
    """
    A tree widget that is loaded from and saved to a config
    """
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)

        self.schema = kwargs.get('schema', [])
        tree_height = kwargs.get('tree_height', None)

        self.readonly = kwargs.get('readonly', False)
        tree_width = kwargs.get('tree_width', 200)
        tree_header_hidden = kwargs.get('tree_header_hidden', False)
        layout_type = kwargs.get('layout_type', QVBoxLayout)

        self.layout = layout_type(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        tree_layout = QVBoxLayout()
        self.tree_buttons = TreeButtonsWidget(parent=self)
        self.tree_buttons.btn_add.clicked.connect(self.add_item)
        self.tree_buttons.btn_del.clicked.connect(self.delete_item)

        self.tree = BaseTreeWidget(parent=self)
        # self.tree.setFixedWidth(tree_width)
        if tree_height:
            self.tree.setFixedHeight(tree_height)
        self.tree.itemChanged.connect(self.field_edited)
        self.tree.itemSelectionChanged.connect(self.on_item_selected)
        self.tree.setHeaderHidden(tree_header_hidden)
        self.tree.setSortingEnabled(False)

        tree_layout.addWidget(self.tree_buttons)
        tree_layout.addWidget(self.tree)
        self.layout.addLayout(tree_layout)

        self.tree.move(-15, 0)

    def build_schema(self):
        schema = self.schema
        if not schema:
            return

        self.tree.build_columns_from_schema(schema)
        # self.tree.setColumnCount(len(schema))
        # # add columns to tree from schema list
        # for i, header_dict in enumerate(schema):
        #     column_visible = header_dict.get('visible', True)
        #     column_width = header_dict.get('width', None)
        #     column_stretch = header_dict.get('stretch', None)
        #     if column_width:
        #         self.tree.setColumnWidth(i, column_width)
        #     if column_stretch:
        #         self.tree.header().setSectionResizeMode(i, QHeaderView.Stretch)
        #     self.tree.setColumnHidden(i, not column_visible)
        #
        # headers = [header_dict['text'] for header_dict in self.schema]
        # self.tree.setHeaderLabels(headers)

    def load(self):
        with block_signals(self.tree):
            self.tree.clear()

            row_data_json_str = next(iter(self.config.values()), None)
            if row_data_json_str is None:
                return
            data = json.loads(row_data_json_str)

            # col_names = [col['text'] for col in self.schema]
            for row_dict in data:
                # values = [row_dict.get(col_name, '') for col_name in col_names]
                self.add_new_entry(row_dict)

    def add_new_entry(self, row_dict, icon=None):
        with block_signals(self.tree):
            col_values = [row_dict.get(col_schema.get('key', col_schema['text'].replace(' ', '_').lower()), None)
                          for col_schema in self.schema]

            item = QTreeWidgetItem(self.tree, [str(v) for v in col_values])

            if self.readonly:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            else:
                item.setFlags(item.flags() | Qt.ItemIsEditable)

            for i, col_schema in enumerate(self.schema):
                type = col_schema.get('type', None)
                width = col_schema.get('width', None)
                default = col_schema.get('default', '')
                key = col_schema.get('key', col_schema['text'].replace(' ', '_').lower())
                val = row_dict.get(key, default)
                if type == QPushButton:
                    btn_func = col_schema.get('func', None)
                    btn_partial = partial(btn_func, row_dict)
                    btn_icon_path = col_schema.get('icon', '')
                    pixmap = colorize_pixmap(QPixmap(btn_icon_path))
                    self.tree.setItemIconButtonColumn(item, i, pixmap, btn_partial)
                elif type == bool:
                    widget = QCheckBox()
                    # val = row_data[i]
                    self.tree.setItemWidget(item, i, widget)
                    widget.setChecked(val)
                    widget.stateChanged.connect(self.update_config)
                elif type == 'RoleComboBox':
                    widget = RoleComboBox()
                    widget.setFixedWidth(100)
                    index = widget.findData(val)
                    widget.setCurrentIndex(index)
                    widget.currentIndexChanged.connect(self.update_config)
                    self.tree.setItemWidget(item, i, widget)
                elif isinstance(type, tuple):
                    widget = BaseComboBox()
                    widget.addItems(type)
                    widget.setCurrentText(str(val))
                    if width:
                        widget.setFixedWidth(width)
                    widget.currentIndexChanged.connect(self.update_config)
                    self.tree.setItemWidget(item, i, widget)

            if icon:
                item.setIcon(0, QIcon(icon))


            # for i in range(len(key_values)):
            #     col_schema = self.schema[i]
            #     type = col_schema.get('type', None)
            #     width = col_schema.get('width', None)
            #     if type == QPushButton:
            #         btn_func = col_schema.get('func', None)
            #         btn_partial = partial(btn_func, row_data)
            #         btn_icon_path = col_schema.get('icon', '')
            #         pixmap = colorize_pixmap(QPixmap(btn_icon_path))
            #         self.tree.setItemIconButtonColumn(item, i, pixmap, btn_partial)
            #     elif type == bool:
            #         widget = QCheckBox()
            #         val = row_data[i]
            #         self.tree.setItemWidget(item, i, widget)
            #         widget.setChecked(val)
            #         widget.stateChanged.connect(self.update_config)
            #     elif type == 'RoleComboBox':
            #         widget = RoleComboBox()
            #         widget.setFixedWidth(100)
            #         index = widget.findData(row_data[i])
            #         widget.setCurrentIndex(index)
            #         widget.currentIndexChanged.connect(self.update_config)
            #         self.tree.setItemWidget(item, i, widget)
            #     elif isinstance(type, tuple):
            #         widget = BaseComboBox()
            #         widget.addItems(type)
            #         widget.setCurrentText(str(row_data[i]))
            #         if width:
            #             widget.setFixedWidth(width)
            #         widget.currentIndexChanged.connect(self.update_config)
            #         self.tree.setItemWidget(item, i, widget)
            #
            # if icon:
            #     item.setIcon(0, QIcon(icon))

    def field_edited(self, item):
        self.update_config()

    def add_item(self, row_dict=None, icon=None):
        if row_dict is None:
            row_dict = {col.get('key', col['text'].replace(' ', '_').lower()): col.get('default', '')
                        for col in self.schema}
                #col.get('default', '') for col in self.schema]
        self.add_new_entry(row_dict, icon)
        self.update_config()
        # self.load_config()

    def delete_item(self):
        item = self.tree.currentItem()
        if item is None:
            return

        content_field = [i for i, col in enumerate(self.schema) if col.get('key', col['text'].replace(' ', '_').lower()) == 'content']
        if content_field:
            item_content = item.text(content_field[0])
            if item_content != '':
                retval = display_messagebox(
                    icon=QMessageBox.Warning,
                    title="Delete item",
                    text="Are you sure you want to delete this item?",
                    buttons=QMessageBox.Yes | QMessageBox.No,
                )
                if retval != QMessageBox.Yes:
                    return False

        self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))
        self.update_config()

    def on_item_selected(self):
        pass


# class ConfigJsonWorkflow(ConfigWidget):



class ConfigJsonFileTree(ConfigJsonTree):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent, **kwargs)
        self.setAcceptDrops(True)

        # remove last stretch
        self.tree_buttons.layout.takeAt(self.tree_buttons.layout.count() - 1)

        self.btn_add_folder = IconButton(
            parent=self,
            icon_path=':/resources/icon-new-folder.png',
            tooltip='Add Folder',
            size=18,
        )
        self.btn_add_folder.clicked.connect(self.add_folder)
        self.tree_buttons.layout.addWidget(self.btn_add_folder)
        self.tree_buttons.layout.addStretch(1)

    def load(self):
        with block_signals(self.tree):
            self.tree.clear()

            row_data_json_str = next(iter(self.config.values()), None)
            if row_data_json_str is None:
                return
            data = json.loads(row_data_json_str)

            # col_names = [col['text'] for col in self.schema]
            for row_dict in data:
                # values = [row_dict.get(col_name, '') for col_name in col_names]

                path = row_dict['location']
                icon_provider = QFileIconProvider()
                icon = icon_provider.icon(QFileInfo(path))
                if icon is None or isinstance(icon, QIcon) is False:
                    icon = QIcon()

                self.add_new_entry(row_dict, icon=icon)

    def add_item(self, column_vals=None, icon=None):
        with block_pin_mode():
            file_dialog = QFileDialog()
            file_dialog.setFileMode(QFileDialog.ExistingFile)
            file_dialog.setOption(QFileDialog.ShowDirsOnly, False)
            file_dialog.setFileMode(QFileDialog.Directory)
            # fd.setStyleSheet("QFileDialog { color: black; }")
            path, _ = file_dialog.getOpenFileName(self, "Choose Files", "", options=file_dialog.Options())

        if path:
            self.add_path(path)

    def add_folder(self):
        with block_pin_mode():
            file_dialog = QFileDialog()
            file_dialog.setFileMode(QFileDialog.Directory)
            file_dialog.setOption(QFileDialog.ShowDirsOnly, True)
            path = file_dialog.getExistingDirectory(self, "Choose Directory", "")
            if path:
                self.add_path(path)

    def add_path(self, path):
        filename = os.path.basename(path)
        is_dir = os.path.isdir(path)
        row_dict = {'filename': filename, 'location': path, 'is_dir': is_dir}

        icon_provider = QFileIconProvider()
        icon = icon_provider.icon(QFileInfo(path))
        if icon is None or isinstance(icon, QIcon) is False:
            icon = QIcon()

        super().add_item(row_dict, icon)

    def dragEnterEvent(self, event):
        # Check if the event contains file paths to accept it
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        # Check if the event contains file paths to accept it
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        # Get the list of URLs from the event
        urls = event.mimeData().urls()

        # Extract local paths from the URLs
        paths = [url.toLocalFile() for url in urls]

        for path in paths:
            self.add_path(path)

        event.acceptProposedAction()


class ConfigJsonToolTree(ConfigJsonTree):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent, **kwargs)
        self.tree.itemDoubleClicked.connect(self.goto_tool)

    def load(self):
        with block_signals(self.tree):
            self.tree.clear()

            row_data_json_str = next(iter(self.config.values()), None)
            if row_data_json_str is None:
                return
            data = json.loads(row_data_json_str)

            # col_names = [col['text'] for col in self.schema]
            for row_dict in data:
                # values = [row_dict.get(col_name, '') for col_name in col_names]
                icon = colorize_pixmap(QPixmap(':/resources/icon-tool.png'))
                self.add_new_entry(row_dict, icon)

    def add_item(self, column_vals=None, icon=None):
        list_dialog = ListDialog(
            parent=self,
            title='Choose Tool',
            list_type='TOOL',
            callback=self.add_tool,
            # multi_select=True,
        )
        list_dialog.open()

    def add_tool(self, item, _):
        item = item.data(Qt.UserRole)
        icon = colorize_pixmap(QPixmap(':/resources/icon-tool.png'))
        super().add_item(item, icon)

    def goto_tool(self, item):
        from src.gui.components.agent_settings import find_main_widget
        tool_id = item.text(1)
        main = find_main_widget(self)
        main.sidebar.btn_settings.click()
        main.page_settings.settings_sidebar.page_buttons['Tools'].click()
        tools_tree = main.page_settings.pages['Tools'].tree
        # select the tool
        for i in range(tools_tree.topLevelItemCount()):
            if tools_tree.topLevelItem(i).text(1) == tool_id:
                tools_tree.setCurrentItem(tools_tree.topLevelItem(i))

        pass
        # self.main.page_tools.goto_tool(tool_name)


class ConfigPlugin(ConfigWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)

        self.layout = CVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignHCenter)

        self.plugin_type = kwargs.get('plugin_type', 'Agent')
        self.plugin_combo = PluginComboBox(parent=self, plugin_type=self.plugin_type)
        self.plugin_combo.currentIndexChanged.connect(self.plugin_changed)
        self.layout.addWidget(self.plugin_combo)

        self.plugin_config = ConfigFields(parent=self, namespace='plugin', alignment=Qt.AlignHCenter)
        self.layout.addWidget(self.plugin_config)

        self.layout.addStretch(1)

    def build_schema(self):
        from src.utils.plugin import get_plugin_agent_class
        use_plugin = self.plugin_combo.currentData()
        plugin_class = get_plugin_agent_class(use_plugin, None)

        self.plugin_config.schema = getattr(plugin_class, 'schema', [])
        self.plugin_config.build_schema()

    def load(self):
        with block_signals(self.plugin_combo):
            # find where data = self.config['info.use_plugin']
            use_plugin = self.parent.config.get('info.use_plugin', '')
            index = self.plugin_combo.findData(use_plugin)
            self.plugin_combo.setCurrentIndex(index)
            self.build_schema()
            self.plugin_config.load()

    def get_config(self):
        config = {'info.use_plugin': self.plugin_combo.currentData()}
        config.update(self.plugin_config.get_config())
        return config

    def plugin_changed(self):
        self.build_schema()
        self.plugin_config.update_config()


class ConfigCollection(ConfigWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.content = None
        self.pages = {}
        self.settings_sidebar = None

    def load(self):
        # for page in self.pages.values():
        #     page.load()
        current_page = self.content.currentWidget()
        if current_page and hasattr(current_page, 'load'):
            current_page.load()

        if getattr(self, 'settings_sidebar', None):
            self.settings_sidebar.load()


class ConfigPages(ConfigCollection):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.layout = CVBoxLayout(self)
        self.content = QStackedWidget(self)

    def build_schema(self):
        """Build the widgets of all pages from `self.pages`"""
        for page_name, page in self.pages.items():
            if hasattr(page, 'build_schema'):
                page.build_schema()
            self.content.addWidget(page)

        self.settings_sidebar = self.ConfigSidebarWidget(parent=self)

        layout = QHBoxLayout()
        layout.addWidget(self.settings_sidebar)
        layout.addWidget(self.content)
        self.layout.addLayout(layout)

    class ConfigSidebarWidget(QWidget):
        def __init__(self, parent, width=None):
            super().__init__(parent=parent)

            self.parent = parent
            self.setAttribute(Qt.WA_StyledBackground, True)
            self.setProperty("class", "sidebar")
            if width:
                self.setFixedWidth(width)

            self.page_buttons = {
                key: self.Settings_SideBar_Button(parent=self, text=key) for key in self.parent.pages.keys()
            }
            if len(self.page_buttons) == 0:
                return

            first_button = next(iter(self.page_buttons.values()))
            first_button.setChecked(True)

            self.layout = CVBoxLayout(self)
            self.layout.setContentsMargins(10, 0, 10, 0)

            self.button_group = QButtonGroup(self)

            i = 0
            for _, btn in self.page_buttons.items():
                self.button_group.addButton(btn, i)
                self.layout.addWidget(btn)
                i += 1

            self.button_group.buttonToggled[QAbstractButton, bool].connect(self.onButtonToggled)

        def load(self):
            pass

        def onButtonToggled(self, button, checked):
            if checked:
                index = self.button_group.id(button)
                self.parent.content.setCurrentIndex(index)
                self.parent.content.currentWidget().load()

        class Settings_SideBar_Button(QPushButton):
            def __init__(self, parent, text=''):
                super().__init__()
                self.setProperty("class", "menuitem")
                self.setText(self.tr(text))  # todo - translate
                self.setCheckable(True)
                self.font = QFont()
                self.font.setPointSize(13)
                self.setFont(self.font)


class ConfigTabs(ConfigCollection):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.layout = CVBoxLayout(self)
        self.content = QTabWidget(self)
        self.content.currentChanged.connect(self.load)

    def build_schema(self):
        """Build the widgets of all tabs from `self.tabs`"""
        for tab_name, tab in self.pages.items():
            if hasattr(tab, 'build_schema'):
                tab.build_schema()
            self.content.addTab(tab, tab_name)

        layout = QHBoxLayout()
        layout.addWidget(self.content)
        self.layout.addLayout(layout)


def get_widget_value(widget):
    if isinstance(widget, CircularImageLabel):
        return widget.avatar_path
    elif isinstance(widget, ColorPickerWidget):
        return widget.get_color()
    elif isinstance(widget, ModelComboBox):
        return widget.currentData()
    elif isinstance(widget, QCheckBox):
        return widget.isChecked()
    elif isinstance(widget, QLineEdit):
        return widget.text()
    elif isinstance(widget, QComboBox):
        return widget.currentText()
    elif isinstance(widget, QSpinBox):
        return widget.value()
    elif isinstance(widget, QDoubleSpinBox):
        return widget.value()
    elif isinstance(widget, QTextEdit):
        return widget.toPlainText()
    else:
        raise Exception(f'Widget not implemented: {type(widget)}')


def CVBoxLayout(parent=None):
    layout = QVBoxLayout(parent)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    return layout


def CHBoxLayout(parent=None):
    layout = QHBoxLayout(parent)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    return layout
