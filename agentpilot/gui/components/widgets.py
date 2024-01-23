import importlib
import inspect
import logging
import os

from PySide6.QtWidgets import *
from PySide6.QtCore import Signal, QSize
from PySide6.QtGui import QPixmap, QPalette, QColor, QIcon, QFont, Qt, QStandardItemModel, QStandardItem

from agentpilot.utils import sql, resources_rc
from agentpilot.gui.style import TEXT_COLOR, PRIMARY_COLOR, SECONDARY_COLOR
from agentpilot.utils.helpers import block_pin_mode
from agentpilot.utils.plugin import get_plugin_agent_class


class NoWheelSpinBox(QSpinBox):
    """A SpinBox that does not react to mouse wheel events."""

    def wheelEvent(self, event):
        event.ignore()


class NoWheelComboBox(QComboBox):
    """A SpinBox that does not react to mouse wheel events."""

    def wheelEvent(self, event):
        event.ignore()


class ContentPage(QWidget):
    def __init__(self, main, title=''):
        super().__init__(parent=main)

        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.back_button = Back_Button(main)
        self.label = QLabel(title)

        # print('#431')
        self.font = QFont()
        self.font.setPointSize(15)
        self.label.setFont(self.font)
        self.label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.title_layout = QHBoxLayout()
        self.title_layout.setSpacing(20)
        self.title_layout.addWidget(self.back_button)
        self.title_layout.addWidget(self.label)

        self.title_container = QWidget()
        self.title_container.setLayout(self.title_layout)

        self.layout.addWidget(self.title_container)

        if title != 'Agents':
            self.title_layout.addStretch()


class ConfigPages(QWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.layout = QVBoxLayout(self)
        self.content = QStackedWidget(self)
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

    def load(self):
        self.content.currentWidget().load()
        self.settings_sidebar.load()

    def get_current_config(self):
        pass

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


class ConfigPageWidget(QWidget):
    def __init__(self, namespace='', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.namespace = namespace
        self.layout = QVBoxLayout(self)
        self.schema = None

    def build_schema(self):
        schema = self.schema
        # self.clear_layout()
        row_layout = None
        last_row_key = None
        for i, param_dict in enumerate(schema):
            param_text = param_dict['text']
            param_type = param_dict['type']
            param_default = param_dict['default']
            param_width = param_dict.get('width', None)
            num_lines = param_dict.get('num_lines', 1)
            row_key = param_dict.get('row_key', None)
            label_align = param_dict.get('label_align', 'left')

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
            setattr(self, param_text, widget)
            # self.connect_signal(widget)

            param_layout = QHBoxLayout() if label_align == 'left' else QVBoxLayout()
            param_label = QLabel(param_text)
            param_label.setAlignment(Qt.AlignRight if label_align == 'left' else Qt.AlignLeft)

            param_layout.addWidget(param_label)
            param_layout.addWidget(widget)

            if row_layout:
                row_layout.addLayout(param_layout)
            else:
                self.layout.addLayout(param_layout)

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
            widget = CComboBox()
            widget.addItems(param_type)
            widget.setCurrentText(str(default_value))
            width = param_width or 150
        else:
            raise ValueError(f'Unknown param type: {param_type}')

        widget.setProperty('config_key', param_text)
        widget.setFixedWidth(width)

        return widget

    def connect_signal(self, widget):
        if isinstance(widget, QCheckBox):
            widget.stateChanged.connect(self.parent.parent.update_agent_config)
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(self.parent.parent.update_agent_config)
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(self.parent.parent.update_agent_config)
        elif isinstance(widget, QSpinBox):
            widget.valueChanged.connect(self.parent.parent.update_agent_config)
        elif isinstance(widget, QDoubleSpinBox):
            widget.valueChanged.connect(self.parent.parent.update_agent_config)
        elif isinstance(widget, QTextEdit):
            widget.textChanged.connect(self.parent.parent.update_agent_config)
        else:
            raise Exception(f'Widget not implemented: {type(widget)}')

    def get_config(self):
        config = {}
        for param_dict in self.schema:
            param_text = param_dict['text']

            widget = getattr(self, param_text)
            config_key = f"{self.namespace}.{param_text}" if self.namespace else param_text
            config[config_key] = get_widget_value(widget)

        return config


def get_widget_value(widget):
    if isinstance(widget, QCheckBox):
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


class DynamicPluginSettings(ConfigPageWidget):
    def __init__(self, parent, plugin_combo):  # ), plugin_type='agent'):
        super().__init__()
        self.parent = parent
        self.plugin_combo = plugin_combo

        # self.layout = QGridLayout(self)
        # self.setLayout(self.layout)
        # self.plugin_combo.currentIndexChanged.connect(self.update_agent_plugin)  # update_agent_config)

    # def update_agent_plugin(self):
    #     from agentpilot.context.base import Context
    #     main = self.parent.parent.main
    #     main.page_chat.context = Context(main)
    #     self.parent.parent.update_agent_config()

    def load(self):
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

    def clear_layout(self):
        for i in reversed(range(self.layout.count())):
            widget = self.layout.itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()


class IconButton(QPushButton):
    def __init__(self, parent, icon_path, size=25):
        super().__init__(parent=parent)
        self.parent = parent
        self.icon = QIcon(QPixmap(icon_path))
        self.setIcon(self.icon)
        icon_size = int(size * 0.75)
        self.setFixedSize(size, size)
        self.setIconSize(QSize(icon_size, icon_size))


class Back_Button(QPushButton):
    def __init__(self, main):
        super().__init__(parent=main)
        self.main = main
        self.clicked.connect(self.go_back)
        self.icon = QIcon(QPixmap(":/resources/icon-back.png"))
        self.setIcon(self.icon)
        self.setFixedSize(40, 40)
        self.setIconSize(QSize(30, 30))

    def go_back(self):
        self.main.content.setCurrentWidget(self.main.page_chat)
        self.main.sidebar.btn_new_context.setChecked(True)


class BaseTableWidget(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(18)
        # self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.setSortingEnabled(True)
        # self.setMouseTracking(True)
        # self.setContextMenuPolicy(Qt.CustomContextMenu)
        # self.customContextMenuRequested.connect(self.open_menu)
        self.setShowGrid(False)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setColumnHidden(0, True)

        palette = self.palette()
        palette.setColor(QPalette.Highlight, '#0dffffff')
        palette.setColor(QPalette.HighlightedText, QColor(f'#cc{TEXT_COLOR}'))  # Setting selected text color to purple
        palette.setColor(QPalette.Text, QColor(TEXT_COLOR))  # Setting unselected text color to purple
        self.setPalette(palette)

        # Set the horizontal header properties (column headers)
        horizontalHeader = self.horizontalHeader()
        # Use a style sheet to change the background color of the column headers
        horizontalHeader.setStyleSheet(
            "QHeaderView::section {"
            f"background-color: {PRIMARY_COLOR};"  # Red background
            f"color: {TEXT_COLOR};"  # White text color
            "padding-left: 4px;"  # Padding from the left edge
            "}"
        )
        horizontalHeader.setDefaultAlignment(Qt.AlignLeft)


class ColorPickerButton(QPushButton):
    colorChanged = Signal(str)  # Define a new signal that passes a string

    def __init__(self):
        super().__init__()
        self.color = None
        self.setFixedSize(24, 24)  # Or any other appropriate size for your square
        self.setStyleSheet("background-color: white; border: none;")  # Default color and style
        self.clicked.connect(self.pick_color)

    def pick_color(self):
        current_color = self.color if self.color else Qt.white
        with block_pin_mode():
            color = QColorDialog.getColor(current_color, self)

        if color.isValid():
            self.color = color
            self.setStyleSheet(f"background-color: {color.name()}; border: none;")
            self.colorChanged.emit(color.name())  # Emit the signal with the new color name

    def set_color(self, hex_color):
        color = QColor(hex_color)
        if color.isValid():
            self.color = color
            self.setStyleSheet(f"background-color: {color.name()}; border: none;")

    def get_color(self):
        return self.color.name() if self.color and self.color.isValid() else None


class CComboBox(QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_pin_state = None
        self.setItemDelegate(NonSelectableItemDelegate(self))
        self.setFixedWidth(150)

    def showPopup(self):
        from agentpilot.gui import main
        self.current_pin_state = main.PIN_MODE
        main.PIN_MODE = True
        super().showPopup()

    def hidePopup(self):
        from agentpilot.gui import main
        super().hidePopup()
        if self.current_pin_state is None:
            return
        main.PIN_MODE = self.current_pin_state


class PluginComboBox(CComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setItemDelegate(AlignDelegate(self))
        self.setFixedWidth(175)
        self.setStyleSheet(
            "QComboBox::drop-down {border-width: 0px;} QComboBox::down-arrow {image: url(noimg); border-width: 0px;}")
        self.load()

    def load(self):
        from agentpilot.agent.base import Agent
        self.clear()
        self.addItem("Choose Plugin", "")

        plugins_package = importlib.import_module("agentpilot.plugins")
        plugins_dir = os.path.dirname(plugins_package.__file__)

        # Iterate over all directories in 'plugins_dir'
        for plugin_name in os.listdir(plugins_dir):
            plugin_path = os.path.join(plugins_dir, plugin_name)

            # Make sure it's a directory
            if not os.path.isdir(plugin_path):
                continue

            try:
                agent_module = importlib.import_module(f"agentpilot.plugins.{plugin_name}.modules.agent_plugin")
            # if ModuleNotFoundError

            except ImportError as e:
                # This plugin doesn't have a 'agent_plugin' module, OR, it has an import error todo
                continue

            # Iterate over all classes in the 'agent_plugin' module
            for name, obj in inspect.getmembers(agent_module):
                if inspect.isclass(obj) and issubclass(obj, Agent) and obj != Agent:
                    self.addItem(name.replace('_', ' '), plugin_name)

    def paintEvent(self, event):
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()

        # Init style options with the current state of this widget
        self.initStyleOption(option)

        # Draw the combo box without the current text (removes the default left-aligned text)
        painter.setPen(self.palette().color(QPalette.Text))
        painter.drawComplexControl(QStyle.CC_ComboBox, option)

        # Manually draw the text, centered
        text_rect = self.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxEditField)
        text_rect.adjust(18, 0, 0, 0)  # left, top, right, bottom

        current_text = self.currentText()
        painter.drawText(text_rect, Qt.AlignCenter, current_text)


class ModelComboBox(CComboBox):
    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)

        self.load()

    def load(self):
        self.clear()

        model = QStandardItemModel()
        self.setModel(model)

        models = sql.get_results("""
            SELECT
                m.alias,
                m.model_name,
                a.name AS api_name
            FROM models m
            LEFT JOIN apis a
                ON m.api_id = a.id
            ORDER BY
                a.name,
                m.alias
        """)

        current_api = None

        if self.first_item:
            first_item = QStandardItem(self.first_item)
            first_item.setData(0, Qt.UserRole)
            model.appendRow(first_item)

        for alias, model_name, api_id in models:
            if current_api != api_id:
                header_item = QStandardItem(api_id)
                header_item.setData('header', Qt.UserRole)
                header_item.setEnabled(False)
                model.appendRow(header_item)

                current_api = api_id

            item = QStandardItem(alias)
            item.setData(model_name, Qt.UserRole)
            model.appendRow(item)


class APIComboBox(CComboBox):
    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)

        self.load()

    def load(self):
        logging.debug('Loading APIComboBox')
        self.clear()
        models = sql.get_results("SELECT name, id FROM apis")
        if self.first_item:
            self.addItem(self.first_item, 0)
        for model in models:
            self.addItem(model[0], model[1])


class RoleComboBox(CComboBox):
    def __init__(self, *args, **kwargs):
        logging.debug('Init RoleComboBox')
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)

        self.load()

    def load(self):
        logging.debug('Loading RoleComboBox')
        self.clear()
        models = sql.get_results("SELECT name, id FROM roles")
        if self.first_item:
            self.addItem(self.first_item, 0)
        for model in models:
            self.addItem(model[0].title(), model[1])


class NonSelectableItemDelegate(QStyledItemDelegate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def paint(self, painter, option, index):
        is_header = index.data(Qt.UserRole) == 'header'
        if is_header:
            # Modify the style of headers here as you like, for example, bold or different background
            option.font.setBold(True)
        super().paint(painter, option, index)

    def editorEvent(self, event, model, option, index):
        if index.data(Qt.UserRole) == 'header':
            # Disable selection/editing of header items by consuming the event
            return True
        return super().editorEvent(event, model, option, index)


class AlignDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        option.displayAlignment = Qt.AlignCenter
        super(AlignDelegate, self).paint(painter, option, index)