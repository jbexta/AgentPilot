
import json

from PySide6.QtWidgets import *
from PySide6.QtGui import QFont, Qt

from agentpilot.gui.style import SECONDARY_COLOR
from agentpilot.utils.helpers import block_signals
from agentpilot.gui.widgets.base import BaseComboBox, ModelComboBox, PluginComboBox
from agentpilot.utils.plugin import get_plugin_agent_class


class ConfigPages(QWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.content = QStackedWidget(self)
        self.config = {}
        self.pages = {}
        self.settings_sidebar = None

    def create_pages(self):
        for page_name, page in self.pages.items():
            if hasattr(page, 'build_schema'):
                page.build_schema()
            self.content.addWidget(page)

        self.settings_sidebar = self.ConfigSidebarWidget(parent=self)

        layout = QHBoxLayout(self)
        layout.addWidget(self.settings_sidebar)
        layout.addWidget(self.content)
        self.layout.addLayout(layout)

    def load_config(self, json_config):
        self.config = json.loads(json_config) if json_config else {}
        for page in self.pages.values():
            page.load_config()

    def update_config(self):
        self.config = {}
        for page_name, page in self.pages.items():
            self.config.update(page.config)

        if hasattr(self, 'save_config'):
            self.save_config()

    def save_config(self):  # , table, field_key_values, where_key_values):
        """Saves the config to database when modified"""
        pass
        # query = f"UPDATE {table} SET config = ?"

    def load(self):
        self.content.currentWidget().load()
        self.settings_sidebar.load()

    # def load_config(self):
    #     for _, page in self.pages.items():
    #         page.load_config()

    # def get_all_config(self):
    #     all_config = {}
    #     for page_name, page in self.pages.items():
    #         all_config.update(page.config)
    #
    #     return all_config

    class ConfigSidebarWidget(QWidget):
        def __init__(self, parent, width=100):
            super().__init__(parent=parent)
            self.parent = parent
            self.setAttribute(Qt.WA_StyledBackground, True)
            self.setProperty("class", "sidebar")
            self.setFixedWidth(width)

            self.page_buttons = {
                key: self.Settings_SideBar_Button(parent=self, text=key) for key in self.parent.pages.keys()
            }

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
                # self.setStyleSheet("QPushButton { text-align: left; }")


class ConfigFieldsWidget(QWidget):
    def __init__(self, namespace='', alignment=Qt.AlignLeft, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.namespace = namespace
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(alignment)
        self.config = {}
        self.schema = []
        self.alignment = None
        self.label_width = None

    def build_schema(self):
        schema = self.schema
        if not schema:
            return
        self.clear_layout(self.layout)

        row_layout = None
        last_row_key = None
        for i, param_dict in enumerate(schema):
            param_text = param_dict['text']
            key = param_dict.get('key', param_text.replace(' ', '_').lower())
            param_type = param_dict['type']
            param_default = param_dict['default']
            param_width = param_dict.get('width', None)
            num_lines = param_dict.get('num_lines', 1)
            row_key = param_dict.get('row_key', None)
            label_align = param_dict.get('label_align', 'left')
            label_width = param_dict.get('label_width', None) or self.label_width

            if row_key is not None and row_layout is None:
                row_layout = QHBoxLayout()
            elif row_key is not None and row_layout is not None and row_key != last_row_key:
                self.layout.addLayout(row_layout)
                row_layout = QHBoxLayout()
            elif row_key is None and row_layout is not None:
                self.layout.addLayout(row_layout)
                row_layout = None

            last_row_key = row_key

            # current_value = self.parent.parent.agent_config.get(f'plugin.{param_text}', None)
            # if current_value is not None:
            #     param_default = current_value

            widget = self.create_widget_by_type(
                param_text=param_text,
                param_type=param_type,
                default_value=param_default,
                param_width=param_width,
                num_lines=num_lines)
            setattr(self, key, widget)
            self.connect_signal(widget)

            param_layout = QHBoxLayout() if label_align == 'left' else QVBoxLayout()
            param_label = QLabel(param_text)
            # param_label.setAlignment(Qt.AlignRight if label_align == 'left' else Qt.AlignLeft)
            param_label.setAlignment(Qt.AlignLeft)
            if label_width:
                param_label.setFixedWidth(label_width)

            param_layout.addWidget(param_label)
            param_layout.addWidget(widget)
            param_layout.addStretch(1)

            if row_layout:
                row_layout.addLayout(param_layout)
            else:
                self.layout.addLayout(param_layout)

        if row_layout:
            self.layout.addLayout(row_layout)

        self.layout.addStretch(1)

    def load_config(self):
        parent_config = self.parent.config
        if not parent_config:
            return

        if self.namespace != '':
            self.config = {k: v for k, v in parent_config.items() if k.startswith(f'{self.namespace}.')}
        else:
            self.config = parent_config
        pass

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

    def create_widget_by_type(self, param_text, param_type, default_value, param_width=None, num_lines=1):
        width = param_width or 50
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
            if num_lines == 1:
                widget = QLineEdit()

                widget.setStyleSheet(f"background-color: {SECONDARY_COLOR}; border-radius: 6px;")
            else:
                widget = QTextEdit()
                font_metrics = widget.fontMetrics()
                height = font_metrics.lineSpacing() * num_lines + widget.contentsMargins().top() + widget.contentsMargins().bottom()
                widget.setFixedHeight(height)

            widget.setText(default_value)
            width = param_width or 150
        elif isinstance(param_type, tuple):
            widget = BaseComboBox()
            widget.addItems(param_type)
            widget.setCurrentText(str(default_value))
            width = param_width or 150
        elif param_type == 'ModelComboBox':
            widget = ModelComboBox()
            widget.setCurrentText(str(default_value))
            width = param_width or 150
        elif param_type == 'PluginComboBox':
            widget = PluginComboBox()
            widget.setCurrentText(str(default_value))
            width = param_width or 150
        elif param_type == 'CircularImage':
            pass
        else:
            raise ValueError(f'Unknown param type: {param_type}')

        widget.setProperty('config_key', param_text)
        widget.setFixedWidth(width)

        return widget

    def connect_signal(self, widget):
        if isinstance(widget, QCheckBox):
            widget.stateChanged.connect(self.update_config)  # parent.parent.update_agent_config)
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(self.update_config)  # parent.parent.update_agent_config)
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(self.update_config)  # parent.parent.update_agent_config)
        elif isinstance(widget, QSpinBox):
            widget.valueChanged.connect(self.update_config)  # parent.parent.update_agent_config)
        elif isinstance(widget, QDoubleSpinBox):
            widget.valueChanged.connect(self.update_config)  # parent.parent.update_agent_config)
        elif isinstance(widget, QTextEdit):
            widget.textChanged.connect(self.update_config)  # parent.parent.update_agent_config)
        else:
            raise Exception(f'Widget not implemented: {type(widget)}')

    def set_widget_value(self, widget, value):
        if isinstance(widget, ModelComboBox):
            index = widget.findData(value)
            widget.setCurrentIndex(index)
        elif isinstance(widget, PluginComboBox):
            index = widget.findData(value)
            widget.setCurrentIndex(index)
        elif isinstance(widget, Circular):
            pass
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

    # """Clear all layouts and widgets from the given layout"""
    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                child_layout = item.layout()
                if child_layout is not None:
                    self.clear_layout(child_layout)


    # def save_config(self):
    #     """Bubble the save method to the root config widget, then saves config to database"""
    #     if hasattr(self.parent, 'save_config'):
    #         self.parent.save_config()


def get_widget_value(widget):
    if isinstance(widget, ModelComboBox):
        return widget.currentData()
    elif isinstance(widget, PluginComboBox):
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


# class ConfigMutableListWidget(ConfigFieldsWidget):


class PluginConfigWidget(ConfigFieldsWidget):
    def __init__(self, parent, plugin_combo):  # ), plugin_type='agent'):
        super().__init__()
        self.parent = parent
        self.plugin_combo = plugin_combo

        # self.layout = QGridLayout(self)
        # self.setLayout(self.layout)
        # self.plugin_combo.currentIndexChanged.connect(self.update_agent_plugin)  # update_agent_config)

    def load_plugin(self):
        plugin_class = get_plugin_agent_class(self.plugin_combo.currentData(), None)
        if plugin_class is None:
            self.hide()
            return

        self.schema = getattr(plugin_class, 'extra_params', [])
        self.build_schema()

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