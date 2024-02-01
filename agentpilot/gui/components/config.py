
import json
import logging
from abc import abstractmethod
from functools import partial

from PySide6.QtCore import Signal
from PySide6.QtWidgets import *
from PySide6.QtGui import QFont, Qt, QIcon

from agentpilot.gui.style import SECONDARY_COLOR
from agentpilot.utils.helpers import block_signals, path_to_pixmap, block_pin_mode, display_messagebox
from agentpilot.gui.widgets.base import BaseComboBox, ModelComboBox, PluginComboBox, CircularImageLabel, \
    ColorPickerWidget, FontComboBox, BaseTreeWidget, IconButton
from agentpilot.utils.plugin import get_plugin_agent_class
from agentpilot.utils import sql


# class ConfigWidget(QWidget):
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#
#     def build_schema(self):


class ConfigPages(QWidget):
    def __init__(self, parent):
        super().__init__()  # parent=parent)
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
        if current_widget:
            current_widget.load()
        # self.settings_sidebar.load()

    def load_config(self, json_config):
        """Loads the config dict from an input json string"""
        logging.debug('Loading config of ConfigPages')
        self.config = json.loads(json_config) if json_config else {}
        for page in self.pages.values():
            page.load_config()

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


class ConfigFieldsWidget(QWidget):
    def __init__(self, parent=None, namespace='', alignment=Qt.AlignLeft, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logging.debug('Initializing ConfigFieldsWidget')
        self.parent = parent
        self.namespace = namespace
        self.alignment = Qt.AlignCenter
        self.layout = CVBoxLayout(self)
        self.layout.setAlignment(self.alignment)
        self.config = {}
        self.schema = []
        self.label_width = None

    def build_schema(self):
        """Build the widgets from the schema list"""
        logging.debug('Building schema of ConfigFieldsWidget')
        schema = self.schema
        if not schema:
            return
        self.clear_layout(self.layout)

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

            # current_value = self.parent.parent.agent_config.get(f'plugin.{param_text}', None)
            # if current_value is not None:
            #     param_default = current_value

            widget = self.create_widget(**param_dict)
            setattr(self, key, widget)
            self.connect_signal(widget)

            if hasattr(widget, 'build_schema'):
                widget.build_schema()

            param_layout = CHBoxLayout() if label_position == 'left' else CVBoxLayout()
            param_layout.setContentsMargins(2, 2, 2, 2)
            if label_position is not None:
                param_label = QLabel(param_text)
                param_label.setAlignment(Qt.AlignLeft)
                if label_width:
                    param_label.setFixedWidth(label_width)

                param_layout.addWidget(param_label)
            # else:
            #     param_layout.addStretch(1)

            param_layout.addWidget(widget)
            param_layout.addStretch(1)

            if row_layout:
                row_layout.addLayout(param_layout)
            else:
                param_layout.setAlignment(self.alignment)
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
                config_key = f"{self.namespace}.{key}" if self.namespace else key
                config_value = self.config.get(config_key, None)
                if config_value is not None:
                    self.set_widget_value(widget, config_value)
                else:
                    pass

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
        fill_width = kwargs.get('fill_width', False)

        set_width = param_width or 50
        if param_type == bool:
            widget = QCheckBox()
            widget.setChecked(default_value)
        elif param_type == int:
            widget = QSpinBox()
            widget.setValue(default_value)
        elif param_type == float:
            widget = QDoubleSpinBox()
            widget.setValue(default_value)
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
            widget = ConfigPluginWidget()
            widget.setPlugin(str(default_value))
            set_width = param_width or 175
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

        if fill_width:
            pass  # widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        elif set_width:
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
            index = widget.plugin_combo.findData(value)
            widget.plugin_combo.setCurrentIndex(index)
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
            widget.setCurrentText(value)
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
            size=18,
        )
        self.btn_del = IconButton(
            parent=self,
            icon_path=':/resources/icon-minus.png',
            size=18,
        )

        self.btn_add.setToolTip('Add')
        self.btn_del.setToolTip('Delete')
        self.layout.addWidget(self.btn_add)
        self.layout.addWidget(self.btn_del)
        self.layout.addStretch(1)


class ConfigTreeWidget(QWidget):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent=parent)
        logging.debug('Initializing ConfigTreeWidget')
        self.parent = parent

        self.schema = kwargs.get('schema', [])
        self.query = kwargs.get('query', None)
        self.db_table = kwargs.get('db_table', None)
        self.db_config_field = kwargs.get('db_config_field', 'config')
        self.add_item_prompt = kwargs.get('add_item_prompt', None)
        self.del_item_prompt = kwargs.get('del_item_prompt', None)
        self.config_widget = kwargs.get('config_widget', None)
        self.readonly = kwargs.get('readonly', True)
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

        tree_layout.addWidget(self.tree_buttons)
        tree_layout.addWidget(self.tree)
        self.layout.addLayout(tree_layout)

        if self.config_widget:
            self.layout.addWidget(self.config_widget)

        # self.tree.itemDoubleClicked.connect(self.on_row_double_clicked)
        # self.tree.itemSelectionChanged.connect(self.on_row_selected)
        # self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        # self.tree.customContextMenuRequested.connect(self.show_context_menu)

    def build_schema(self):
        logging.debug('Building schema of ConfigTreeWidget')
        pass
        schema = self.schema
        if not schema:
            return
        # self.tree.clear()

        self.tree.setColumnCount(len(schema))
        # add columns to tree from schema list
        for i, header_dict in enumerate(schema):
            # header_text = header_dict['text']
            # header_type = header_dict.get('type', str)

            # self.tree.setHeaderItem(QTreeWidgetItem(self.tree, [header_text]))

            column_visible = header_dict.get('visible', True)
            column_width = header_dict.get('width', None)
            column_stretch = header_dict.get('stretch', None)
            if column_width:
                self.tree.setColumnWidth(i, column_width)
            if column_stretch:
                self.tree.header().setSectionResizeMode(i, QHeaderView.Stretch)
            self.tree.setColumnHidden(i, not column_visible)
            # self.tree.header().setSectionResizeMode(i, QHeaderView.Stretch)

        headers = [header_dict['text'] for header_dict in self.schema]
        self.tree.setHeaderLabels(headers)

        if self.config_widget:
            self.config_widget.build_schema()

    def load(self):
        """
        Loads the tree widget from the query specified in the constructor.
        """
        if not self.query:
            return
        icon_chat = QIcon(':/resources/icon-chat.png')
        # icon_del = QIcon(':/resources/icon-delete.png')

        with block_signals(self.tree):
            self.tree.clear()  # Clear entire tree widget
            data = sql.get_results(query=self.query)
            for row_data in data:
                item = QTreeWidgetItem(self.tree, [str(v) for v in row_data])

                if not self.readonly:
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)

                for i in range(len(row_data)):
                    col_schema = self.schema[i]
                    type = col_schema.get('type', None)
                    if type == QPushButton:
                        btn_func = col_schema.get('func', None)
                        btn_partial = partial(btn_func, row_data)
                        btn_icon_path = col_schema.get('icon', '')
                        btn_icon = path_to_pixmap(btn_icon_path)
                        self.tree.setItemIconButtonColumn(item, i, btn_icon, btn_partial)

                    image_key = col_schema.get('image_key', None)
                    if image_key:
                        image_index = [i for i, d in enumerate(self.schema) if d.get('key', None) == image_key][0]  # todo dirty
                        image_path = row_data[image_index] or ''  # todo - clean this
                        pixmap = path_to_pixmap(image_path, diameter=25)
                        item.setIcon(i, QIcon(pixmap))

        # set first row selected if exists
        if self.tree.topLevelItemCount() > 0:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    @abstractmethod
    def load_config(self):
        pass

    @abstractmethod
    def get_config(self):
        pass

    @abstractmethod
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
        item = self.tree.currentItem()
        if not item:
            return False

        id = int(item.text(0))
        json_config = json.dumps(self.config_widget.config)
        sql.execute(f"""UPDATE `{self.db_table}` 
                        SET `{self.db_config_field}` = ?
                        WHERE id = ?
                    """, (json_config, id,))

    def field_edited(self, item):
        id = int(item.text(0))
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

        sql.execute(f"INSERT INTO `{self.db_table}` (`name`) VALUES (?)", (text,))
        return True

    def delete_item(self):
        item = self.tree.currentItem()
        if not item:
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

        id = int(item.text(0))
        sql.execute(f"DELETE FROM `{self.db_table}` WHERE `id` = ?", (id,))
        return True

    def on_item_selected(self):
        item = self.tree.currentItem()
        if not item:
            return

        id = int(item.text(0))
        json_config = sql.get_scalar(f"""
            SELECT
                `config`
            FROM `{self.db_table}`
            WHERE id = ?
        """, (id,))
        self.config_widget.load_config(json_config)
        self.config_widget.load()


class ConfigPluginWidget(QWidget):
    pluginSelected = Signal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logging.debug('Initializing ConfigPluginWidget')

        self.schema = kwargs.get('schema', [])
        self.query = kwargs.get('query', None)
        self.plugin_type = kwargs.get('plugin_type', 'agent')

        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.plugin_combo = PluginComboBox()
        self.layout.addWidget(self.plugin_combo)

        self.config_widget = ConfigFieldsWidget()
        self.layout.addWidget(self.config_widget)

        # self.layout.addWidget(self.plugin_combo)
        # # self.plugin_settings = ConfigFieldsWidget(namespace='plugin')
        # self.plugin_combo.currentIndexChanged.connect(self.load_plugin)
        #
        # # self.layout = QGridLayout(self)
        # # self.setLayout(self.layout)
        # # self.plugin_combo.currentIndexChanged.connect(self.update_agent_plugin)  # update_agent_config)
    def setPlugin(self, plugin_name):
        index = self.plugin_combo.findData(plugin_name)
        self.plugin_combo.setCurrentIndex(index)
        self.build_schema()
        # self.load_plugin()

    def build_schema(self):
        use_plugin = self.plugin_combo.currentData()
        plugin_class = get_plugin_agent_class(use_plugin, None)
        if plugin_class is None:
            # self.hide()
            return

        self.config_widget.schema = getattr(plugin_class, 'extra_params', [])
        self.config_widget.build_schema()
        # self.build_schema()
        # self.load_config()
        # self.pluginSelected.emit(self.plugin_combo.currentData())

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