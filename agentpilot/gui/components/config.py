
import json
import logging
from functools import partial
from sqlite3 import IntegrityError

from PySide6.QtCore import Signal
from PySide6.QtWidgets import *
from PySide6.QtGui import QFont, Qt, QIcon, QPixmap

from agentpilot.gui.style import SECONDARY_COLOR
from agentpilot.utils.helpers import block_signals, path_to_pixmap, block_pin_mode, display_messagebox
from agentpilot.gui.widgets.base import BaseComboBox, ModelComboBox, PluginComboBox, CircularImageLabel, \
    ColorPickerWidget, FontComboBox, BaseTreeWidget, IconButton, colorize_pixmap
from agentpilot.utils.plugin import get_plugin_agent_class
from agentpilot.utils import sql


class ConfigFieldsWidget(QWidget):
    def __init__(self, parent=None, namespace='', alignment=Qt.AlignLeft, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logging.debug('Initializing ConfigFieldsWidget')
        self.parent = parent
        self.namespace = namespace
        self.alignment = alignment
        self.layout = CVBoxLayout(self)
        self.layout.setAlignment(self.alignment)
        self.config = {}
        self.schema = []
        self.label_width = kwargs.get('label_width', None)

    def build_schema(self):
        """Build the widgets from the schema list"""
        logging.debug('Building schema of ConfigFieldsWidget')
        self.clear_layout(self.layout)
        schema = self.schema
        if not schema:
            return

        row_layout = None
        last_row_key = None
        for i, param_dict in enumerate(schema):
            param_text = param_dict['text']
            key = param_dict.get('key', param_text.replace(' ', '_').lower())
            row_key = param_dict.get('row_key', None)
            label_position = param_dict.get('label_position', 'left')
            label_width = param_dict.get('label_width', None) or self.label_width

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
            param_layout.setContentsMargins(2, 2, 2, 2)
            param_layout.setAlignment(self.alignment)
            if label_position is not None:
                param_label = QLabel(param_text)
                param_label.setAlignment(Qt.AlignLeft)
                if label_width:
                    param_label.setFixedWidth(label_width)

                param_layout.addWidget(param_label)

            param_layout.addWidget(widget)

            # # if widget is not ConfigPluginWidget:
            # if not isinstance(widget, ConfigPluginWidget):
            param_layout.addStretch(1)  # todo
            # else:
            #     pass

            if row_layout:
                # row_layout.setAlignment(self.alignment)
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
                key = param_dict.get('key', param_text.replace(' ', '_').lower())
                widget = getattr(self, key)
                # else:
                config_key = f"{self.namespace}.{key}" if self.namespace else key
                config_value = self.config.get(config_key, None)
                if config_value is not None:
                    self.set_widget_value(widget, config_value)
                else:
                    self.set_widget_value(widget, param_dict['default'])

                if isinstance(widget, ConfigPluginWidget):
                    widget.load()

    def load_config(self, json_config=None):
        """Loads the config dict from the root config widget"""
        if json_config is not None:
            self.config = json.loads(json_config) if json_config else {}
            self.load()
            return
        else:
            parent_config = self.parent.config
            if not parent_config:
                return

            if self.namespace != '':
                self.config = {k: v for k, v in parent_config.items() if k.startswith(f'{self.namespace}.')}
            else:
                self.config = parent_config

    def get_config(self):
        """Get the config dict of the current config widget"""
        config = {}
        for param_dict in self.schema:
            param_text = param_dict['text']
            param_key = param_dict.get('key', param_text.replace(' ', '_').lower())
            widget = getattr(self, param_key)
            if isinstance(widget, ConfigPluginWidget):
                config.update(widget.config)
            else:
                config_key = f"{self.namespace}.{param_key}" if self.namespace else param_key
                config[config_key] = get_widget_value(widget)

        return config

    def update_config(self):
        """Bubble update config dict to the root config widget"""
        self.config = self.get_config()
        if hasattr(self.parent, 'update_config'):
            self.parent.update_config()

        if hasattr(self, 'save_config'):
            self.save_config()

    def create_widget(self, **kwargs):
        param_type = kwargs['type']
        default_value = kwargs['default']
        param_width = kwargs.get('width', None)
        num_lines = kwargs.get('num_lines', 1)
        text_height = kwargs.get('text_height', None)
        text_alignment = kwargs.get('text_alignment', Qt.AlignLeft)
        background_color = kwargs.get('background_color', SECONDARY_COLOR)
        # fill_width = kwargs.get('fill_width', False)
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
            if not background_color:
                background_color = 'transparent'
            widget.setStyleSheet(f"background-color: {background_color}; border-radius: 6px;")
            widget.setAlignment(text_alignment)

            if text_height:
                font = widget.font()
                font.setPointSize(text_height)
                widget.setFont(font)
            font_metrics = widget.fontMetrics()
            height = font_metrics.lineSpacing() * num_lines + widget.contentsMargins().top() + widget.contentsMargins().bottom()
            widget.setFixedHeight(height)
            widget.setText(default_value)
            set_width = param_width or 150
        elif isinstance(param_type, tuple):
            widget = BaseComboBox()
            widget.addItems(param_type)
            widget.setCurrentText(str(default_value))
            set_width = param_width or 150
        elif param_type == 'ConfigPluginWidget':
            parent = kwargs.get('parent', None)
            widget = ConfigPluginWidget(parent=parent)
            widget.setPlugin(str(default_value))
            set_width = None  # param_width or 175
        elif param_type == 'CircularImageLabel':
            widget = CircularImageLabel()
            widget.setImagePath(str(default_value))
            set_width = widget.width()
        elif param_type == 'ModelComboBox':
            widget = ModelComboBox()
            widget.setCurrentText(str(default_value))
            set_width = param_width or 150
        elif param_type == 'FontComboBox':
            widget = FontComboBox()
            widget.setCurrentText(str(default_value))
            set_width = param_width or 150
        elif param_type == 'ColorPickerWidget':
            widget = ColorPickerWidget()
            widget.setColor(str(default_value))
            set_width = param_width or 25
        else:
            raise ValueError(f'Unknown param type: {param_type}')

        # if fill_width:
        #     raise NotImplementedError()
        if set_width:
            widget.setFixedWidth(set_width)

        return widget

    def connect_signal(self, widget):
        if isinstance(widget, ConfigPluginWidget):
            widget.pluginSelected.connect(self.update_config)
        elif isinstance(widget, CircularImageLabel):
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
        if isinstance(widget, ConfigPluginWidget):
            widget.setPlugin(value)
        elif isinstance(widget, CircularImageLabel):
            widget.setImagePath(value)
        elif isinstance(widget, ColorPickerWidget):
            widget.setColor(value)
        elif isinstance(widget, ModelComboBox):
            index = widget.findData(value)
            widget.setCurrentIndex(index)
        elif isinstance(widget, QCheckBox):
            widget.setChecked(value)
        elif isinstance(widget, QLineEdit):
            widget.setText(value)
        elif isinstance(widget, QComboBox):
            widget.setCurrentText(str(value))
        elif isinstance(widget, QSpinBox):
            widget.setValue(value)
        elif isinstance(widget, QDoubleSpinBox):
            widget.setValue(value)
        elif isinstance(widget, QTextEdit):
            widget.setText(value)
        else:
            raise Exception(f'Widget not implemented: {type(widget)}')

    def clear_layout(self, layout):
        """Clear all layouts and widgets from the given layout"""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                child_layout = item.layout()
                if child_layout is not None:
                    self.clear_layout(child_layout)
        self.layout.setAlignment(self.alignment)


class ConfigComboBox(BaseComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pass


class TreeButtonsWidget(QWidget):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent=parent)
        logging.debug('Initializing TreeButtonsWidget')
        self.layout = QHBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

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

        if parent.folder_key:
            self.btn_new_folder = IconButton(
                parent=self,
                icon_path=':/resources/icon-new-folder.png',
                tooltip='New Folder',
                size=18,
            )
            self.layout.addWidget(self.btn_new_folder)

        self.layout.addStretch(1)


class ConfigTreeWidget(QWidget):
    """
    A widget that displays a tree of items, with buttons to add and delete items.
    Can contain a config widget shown either to the right of the tree or below it,
    representing the config for each item in the tree.
    """
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent=parent)
        logging.debug('Initializing ConfigTreeWidget')
        self.parent = parent

        self.schema = kwargs.get('schema', [])
        self.query = kwargs.get('query', None)
        self.query_params = kwargs.get('query_params', None)
        self.db_table = kwargs.get('db_table', None)
        self.db_config_field = kwargs.get('db_config_field', 'config')
        self.add_item_prompt = kwargs.get('add_item_prompt', None)
        self.del_item_prompt = kwargs.get('del_item_prompt', None)
        self.config_widget = kwargs.get('config_widget', None)
        self.has_config_field = kwargs.get('has_config_field', True)  # todo - remove
        self.readonly = kwargs.get('readonly', True)
        self.folder_key = kwargs.get('folder_key', None)

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

        self.tree = BaseTreeWidget()
        self.tree.setFixedWidth(tree_width)
        self.tree.itemChanged.connect(self.field_edited)
        self.tree.itemSelectionChanged.connect(self.on_item_selected)
        self.tree.setHeaderHidden(tree_header_hidden)
        if not self.config_widget:
            # self.tree.setFixedHeight()
            self.tree.setFixedHeight(575)

        tree_layout.addWidget(self.tree_buttons)
        tree_layout.addWidget(self.tree)
        self.layout.addLayout(tree_layout)

        if not self.add_item_prompt:
            self.tree_buttons.btn_add.hide()

        if self.config_widget:
            self.layout.addWidget(self.config_widget)

    def build_schema(self):
        logging.debug('Building schema of ConfigTreeWidget')
        pass
        schema = self.schema
        if not schema:
            return

        self.tree.setColumnCount(len(schema))
        # add columns to tree from schema list
        for i, header_dict in enumerate(schema):
            column_visible = header_dict.get('visible', True)
            column_width = header_dict.get('width', None)
            column_stretch = header_dict.get('stretch', None)
            if column_width:
                self.tree.setColumnWidth(i, column_width)
            if column_stretch:
                self.tree.header().setSectionResizeMode(i, QHeaderView.Stretch)
            self.tree.setColumnHidden(i, not column_visible)

        headers = [header_dict['text'] for header_dict in self.schema]
        self.tree.setHeaderLabels(headers)

        if self.config_widget:
            self.config_widget.build_schema()

    def load(self):
        """
        Loads the QTreeWidget with folders and agents from the database.
        """
        if not self.query:
            return

        # Load folders and agents
        folder_query = "SELECT id, name, parent_id, type, ordr FROM folders ORDER BY ordr"
        agent_query = self.query  # Your existing agents query should include the folder_id

        with block_signals(self.tree):
            self.tree.clear()

            # Load folders
            folders_data = sql.get_results(query=folder_query)
            folder_items_mapping = {}  # id to QTreeWidgetItem

            for folder_id, name, parent_id, folder_type, order in folders_data:
                parent_item = folder_items_mapping.get(parent_id) if parent_id else self.tree
                folder_item = QTreeWidgetItem(parent_item, [str(name)])
                folder_item.setData(0, Qt.UserRole, 'folder')
                folder_pixmap = colorize_pixmap(QPixmap(':/resources/icon-folder.png'))
                folder_item.setIcon(0,  QIcon(folder_pixmap))
                folder_items_mapping[folder_id] = folder_item

            # Load agents
            agents_data = sql.get_results(query=agent_query, params=self.query_params)
            for agent_data in agents_data:
                folder_id = agent_data[-1]  # Assuming folder_id is the last element of the agent data tuple
                parent_item = folder_items_mapping.get(folder_id) if folder_id else self.tree

                item = QTreeWidgetItem(parent_item, [str(v) for v in agent_data[:-1]])  # Exclude folder_id

                if not self.readonly:
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)

                for i in range(len(agent_data[:-1])):  # Exclude folder_id
                    col_schema = self.schema[i]
                    type = col_schema.get('type', None)
                    if type == QPushButton:
                        btn_func = col_schema.get('func', None)
                        btn_partial = partial(btn_func, agent_data)
                        btn_icon_path = col_schema.get('icon', '')
                        pixmap = colorize_pixmap(QPixmap(btn_icon_path))
                        self.tree.setItemIconButtonColumn(item, i, pixmap, btn_partial)

                    image_key = col_schema.get('image_key', None)
                    if image_key:
                        image_index = [i for i, d in enumerate(self.schema) if d.get('key', None) == image_key][0]  # todo dirty
                        image_paths = agent_data[image_index] or ''  # todo - clean this
                        image_paths_list = image_paths.split(';')
                        pixmap = path_to_pixmap(image_paths_list, diameter=25)
                        item.setIcon(i, QIcon(pixmap))

        # Additional logic to expand the tree or whatever is needed

    # def load(self):
    #     """
    #     Loads the tree widget from the query specified in the constructor.
    #     """
    #     if not self.query:
    #         return
    #
    #     with block_signals(self.tree):
    #         self.tree.clear()  # Clear entire tree widget
    #         data = sql.get_results(query=self.query, params=self.query_params)
    #         temp_first = True
    #         for row_data in data:
    #             item = QTreeWidgetItem(self.tree, [str(v) for v in row_data])
    #
    #             if temp_first:
    #                 sub_items = [QTreeWidgetItem(item, [str(v) for v in row_data]) for i in range(3)]
    #                 item.setExpanded(True)
    #             temp_first = False
    #
    #             if not self.readonly:
    #                 item.setFlags(item.flags() | Qt.ItemIsEditable)
    #             else:
    #                 item.setFlags(item.flags() & ~Qt.ItemIsEditable)
    #
    #             for i in range(len(row_data)):
    #                 col_schema = self.schema[i]
    #                 type = col_schema.get('type', None)
    #                 if type == QPushButton:
    #                     btn_func = col_schema.get('func', None)
    #                     btn_partial = partial(btn_func, row_data)
    #                     btn_icon_path = col_schema.get('icon', '')
    #                     pixmap = colorize_pixmap(QPixmap(btn_icon_path))
    #                     self.tree.setItemIconButtonColumn(item, i, pixmap, btn_partial)
    #
    #                 image_key = col_schema.get('image_key', None)
    #                 if image_key:
    #                     image_index = [i for i, d in enumerate(self.schema) if d.get('key', None) == image_key][0]  # todo dirty
    #                     image_paths = row_data[image_index] or ''  # todo - clean this
    #                     image_paths_list = image_paths.split(';')
    #                     pixmap = path_to_pixmap(image_paths_list, diameter=25)
    #                     item.setIcon(i, QIcon(pixmap))
    #
    #     # test_subitem = self.tree.topLevelItem(0)  # QTreeWidgetItem(self.tree, [str(v) for v in row_data])
    #     # item = QTreeWidgetItem(self.tree, ['','','','',''])
    #
    #     self.tree.setColumnWidth(0, 1)  # todo
    #
    #     # set first row selected if exists
    #     if self.tree.topLevelItemCount() > 0:
    #         self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def load_folders(self):
        self.folders = sql.get_results(
            query="""
                SELECT
                    id,
                    name,
                    ordr
                FROM folders
                WHERE `type` = ?""",
            params=(self.folder_key,)
        )

    def load_config(self):
        pass

    def get_config(self):
        pass

    def update_config(self):
        """
        When the config widget is changed, calls save_config.
        Does not propagate to the parent.
        """
        self.save_config()

    def save_config(self):
        """
        Saves the config to the database using the tree selected ID.
        """
        id = self.get_current_id()
        json_config = json.dumps(self.config_widget.config)
        sql.execute(f"""UPDATE `{self.db_table}` 
                        SET `{self.db_config_field}` = ?
                        WHERE id = ?
                    """, (json_config, id,))

    def get_current_id(self):
        item = self.tree.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            return None
        return int(item.text(1))

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
            sql.execute(f"INSERT INTO `{self.db_table}` (`name`) VALUES (?)", (text,))
            self.load()
            return True

        except IntegrityError:
            display_messagebox(
                icon=QMessageBox.Warning,
                title='Error',
                text='Item already exists',
            )
            return False

    def delete_item(self):
        id = self.get_current_id()
        if not id:
            return

        dlg_title, dlg_prompt = self.del_item_prompt

        retval = display_messagebox(
            icon=QMessageBox.Warning,
            title=dlg_title,
            text=dlg_prompt,
            buttons=QMessageBox.Yes | QMessageBox.No,
        )
        if retval != QMessageBox.Yes:
            return False

        sql.execute(f"DELETE FROM `{self.db_table}` WHERE `id` = ?", (id,))
        self.load()
        return True

    def on_item_selected(self):
        id = self.get_current_id()
        if not id:
            self.config_widget.setEnabled(False)
            return

        self.config_widget.setEnabled(True)

        if self.has_config_field:
            json_config = sql.get_scalar(f"""
                SELECT
                    `{self.db_config_field}`
                FROM `{self.db_table}`
                WHERE id = ?
            """, (id,))
            self.config_widget.load_config(json_config)

        if hasattr(self.config_widget, 'ref_id'):
            self.config_widget.ref_id = id

        if self.config_widget is not None:
            self.config_widget.load()


# class PluginWidget(ConfigFieldsWidget):


class ConfigPluginWidget(QWidget):
    pluginSelected = Signal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logging.debug('Initializing ConfigPluginWidget')

        self.parent = kwargs.get('parent', None)
        self.schema = kwargs.get('schema', [])
        self.query = kwargs.get('query', None)
        self.plugin_type = kwargs.get('plugin_type', 'agent')

        self.config = {}

        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setAlignment(Qt.AlignHCenter)

        self.plugin_combo = PluginComboBox()
        self.plugin_combo.currentIndexChanged.connect(self.plugin_changed)
        self.layout.addWidget(self.plugin_combo)

        self.config_widget = ConfigFieldsWidget(parent=self,
                                                alignment=Qt.AlignCenter,
                                                namespace='general.plugin')
        self.layout.addWidget(self.config_widget)
        # self.plugin_combo.currentIndexChanged.connect(self.build_schema)
        # self.layout.addWidget(self.plugin_combo)
        # # self.plugin_settings = ConfigFieldsWidget(namespace='plugin')
        #
        # # self.layout = QGridLayout(self)
        # # self.setLayout(self.layout)
        # # self.plugin_combo.currentIndexChanged.connect(self.update_agent_plugin)  # update_agent_config)

    def load(self):
        self.config_widget.load()

    def plugin_changed(self):
        self.build_schema()
        self.pluginSelected.emit(self.plugin_combo.currentData())

    def setPlugin(self, plugin_name):
        index = self.plugin_combo.findData(plugin_name)
        self.plugin_combo.setCurrentIndex(index)
        self.build_schema()
        # self.load_plugin()

    def build_schema(self):
        use_plugin = self.plugin_combo.currentData()
        plugin_class = get_plugin_agent_class(use_plugin, None)
        # if plugin_class is None:
        #     # self.hide()
        #     return

        self.config_widget.schema = getattr(plugin_class, 'extra_params', [])
        self.config_widget.build_schema()
        # self.build_schema()
        # self.load_config()
        # self.pluginSelected.emit(self.plugin_combo.currentData())

    def update_config(self):
        """Bubble update config dict to the root config widget"""
        self.config = {'general.use_plugin': self.plugin_combo.currentData()}
        self.config.update(self.config_widget.get_config())
        if hasattr(self.parent, 'update_config'):
            self.parent.update_config()
        # if hasattr(self, 'save_config'):
        #     self.save_config()

    def update_agent_plugin(self):
        pass
        # from agentpilot.context.base import Context
        # main = self.parent.parent.main
        # main.page_chat.context = Context(main)
        # self.parent.parent.update_agent_config()

    # def load(self):
        # # todo - if structure not changed then don't repopulate pages, only update values
        # plugin_class = get_plugin_agent_class(self.plugin_combo.currentData(), None)
        # if plugin_class is None:
        #     self.hide()
        #     return
        #
        # ext_params = getattr(plugin_class, 'extra_params', [])
        #
        # # Only use one column if there are fewer than 7 params,
        # # otherwise use two columns as before.
        # if len(ext_params) < 7:
        #     widgets_per_column = len(ext_params)
        # else:
        #     widgets_per_column = len(ext_params) // 2 + len(ext_params) % 2
        #
        # self.clear_layout()
        # row, col = 0, 0
        # for i, param_dict in enumerate(ext_params):
        #     param_text = param_dict['text']
        #     param_type = param_dict['type']
        #     param_default = param_dict['default']
        #     param_width = param_dict.get('width', None)
        #     num_lines = param_dict.get('num_lines', 1)
        #
        #     current_value = self.parent.parent.agent_config.get(f'plugin.{param_text}', None)
        #     if current_value is not None:
        #         param_default = current_value
        #
        #     widget = self.create_widget_by_type(
        #         param_text=param_text,
        #         param_type=param_type,
        #         default_value=param_default,
        #         param_width=param_width,
        #         num_lines=num_lines)
        #     setattr(self, param_text, widget)
        #     self.connect_widget(widget)
        #
        #     param_label = QLabel(param_text)
        #     param_label.setAlignment(Qt.AlignRight)
        #     self.layout.addWidget(param_label, row, col * 2)
        #     self.layout.addWidget(widget, row, col * 2 + 1)
        #
        #     row += 1
        #     # Adjust column wrapping based on whether a single or dual column layout is used
        #     if row >= widgets_per_column:
        #         row = 0
        #         col += 1

        self.show()

    # def clear_layout(self):
    #     for i in reversed(range(self.layout.count())):
    #         widget = self.layout.itemAt(i).widget()
    #         if widget is not None:
    #             widget.deleteLater()


class ConfigPages(QWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        logging.debug('Initializing ConfigPages')
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.content = QStackedWidget(self)
        self.config = {}
        self.pages = {}
        self.settings_sidebar = None  # self.ConfigSidebarWidget(parent=self)  # None

    def build_schema(self):
        """Build the widgets of all pages from `self.pages`"""
        logging.debug('Building schema of ConfigPages')
        for page_name, page in self.pages.items():
            if hasattr(page, 'build_schema'):
                page.build_schema()
            self.content.addWidget(page)

        self.settings_sidebar = self.ConfigSidebarWidget(parent=self)

        layout = QHBoxLayout()
        layout.addWidget(self.settings_sidebar)
        layout.addWidget(self.content)
        self.layout.addLayout(layout)

    def load(self):
        """Loads the UI interface, bubbled down from root"""
        logging.debug('Loading ConfigPages')
        current_widget = self.content.currentWidget()
        if hasattr(current_widget, 'load'):
            current_widget.load()
        # self.settings_sidebar.load()

    def load_config(self, json_config):
        """Loads the config dict from an input json string"""
        logging.debug('Loading config of ConfigPages')
        self.config = json.loads(json_config) if json_config else {}
        for page in self.pages.values():
            page.load_config()

            for widget in page.children():
                if hasattr(widget, 'load_config'):
                    widget.load_config()
                # elif isinstance(widget, ConfigFieldsWidget):
                # widget.load_config(json_config)

    def update_config(self):
        """Updates the config dict with the current values of all config widgets"""
        logging.debug('Updating config of ConfigPages')
        self.config = {}
        for page_name, page in self.pages.items():
            page_config = getattr(page, 'config', {})
            self.config.update(page_config)

        if hasattr(self, 'save_config'):
            self.save_config()

    def save_config(self):
        """Saves the config to database when modified"""
        logging.debug('Saving config of ConfigPages')
        pass

    class ConfigSidebarWidget(QWidget):
        def __init__(self, parent, width=100):
            super().__init__(parent=parent)
            logging.debug('Initializing ConfigSidebarWidget')

            self.parent = parent
            self.setAttribute(Qt.WA_StyledBackground, True)
            self.setProperty("class", "sidebar")
            self.setFixedWidth(width)

            self.page_buttons = {
                key: self.Settings_SideBar_Button(parent=self, text=key) for key in self.parent.pages.keys()
            }
            if len(self.page_buttons) == 0:
                return

            first_button = next(iter(self.page_buttons.values()))
            first_button.setChecked(True)

            self.layout = QVBoxLayout(self)
            self.layout.setSpacing(0)
            self.layout.setContentsMargins(0, 0, 0, 0)

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
                self.setText(text)
                self.setFixedSize(parent.width(), 25)
                self.setCheckable(True)
                self.font = QFont()
                self.font.setPointSize(13)
                self.setFont(self.font)


class ConfigTabs(QWidget):
    def __init__(self, parent):
        super().__init__()  # parent=parent)
        logging.debug('Initializing ConfigTabs')
        self.parent = parent
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.content = QTabWidget(self)
        self.config = {}
        self.tabs = {}

    def build_schema(self):
        """Build the widgets of all tabs from `self.tabs`"""
        logging.debug('Building schema of ConfigTabs')
        for tab_name, tab in self.tabs.items():
            if hasattr(tab, 'build_schema'):
                tab.build_schema()
            self.content.addTab(tab, tab_name)

        layout = QHBoxLayout()
        layout.addWidget(self.content)
        self.layout.addLayout(layout)

    def load(self):
        """Loads the UI interface, bubbled down from root"""
        logging.debug('Loading ConfigTabs')
        current_tab = self.content.currentWidget()
        if hasattr(current_tab, 'load'):
            current_tab.load()


def get_widget_value(widget):
    if isinstance(widget, ConfigPluginWidget):
        return widget.plugin_combo.currentData()
    elif isinstance(widget, CircularImageLabel):
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
