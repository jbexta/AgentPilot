import json
import sys
from functools import partial

from PySide6 import QtWidgets
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
from utils.helpers import create_circular_pixmap
from utils import sql, api, config
from utils.sql import check_database
from contextlib import contextmanager

def get_all_children(widget):
    """Recursive function to retrieve all child widgets of a given widget."""
    children = []
    for child in widget.findChildren(QWidget):
        children.append(child)
        children.extend(get_all_children(child))
    return children

@contextmanager
def block_signals(*widgets):
    """Context manager to block signals for a widget and all its child widgets."""
    all_widgets = []
    try:
        # Get all child widgets
        for widget in widgets:
            all_widgets.append(widget)
            all_widgets.extend(get_all_children(widget))

        # Block signals
        for widget in all_widgets:
            widget.blockSignals(True)

        yield
    finally:
        # Unblock signals
        for widget in all_widgets:
            widget.blockSignals(False)


BOTTOM_CORNER_X = 400
BOTTOM_CORNER_Y = 450

PIN_STATE = True

PRIMARY_COLOR = config.get_value('display.primary_color')  # "#363636"
SECONDARY_COLOR = config.get_value('display.secondary_color')  # "#535353"
TEXT_COLOR = config.get_value('display.text_color')  # "#999999"
BORDER_COLOR = "#888"

def get_stylesheet():
    global PRIMARY_COLOR, SECONDARY_COLOR, TEXT_COLOR
    PRIMARY_COLOR = config.get_value('display.primary_color')
    SECONDARY_COLOR = config.get_value('display.secondary_color')
    TEXT_COLOR = config.get_value('display.text_color')
    TEXT_SIZE = config.get_value('display.text_size')

    USER_BUBBLE_BG_COLOR = config.get_value('display.user_bubble_bg_color')
    USER_BUBBLE_TEXT_COLOR = config.get_value('display.user_bubble_text_color')
    ASSISTANT_BUBBLE_BG_COLOR = config.get_value('display.assistant_bubble_bg_color')
    ASSISTANT_BUBBLE_TEXT_COLOR = config.get_value('display.assistant_bubble_text_color')
    CODE_BUBBLE_BG_COLOR = config.get_value('display.code_bubble_bg_color')
    CODE_BUBBLE_TEXT_COLOR = config.get_value('display.code_bubble_text_color')
    ACTION_BUBBLE_BG_COLOR = config.get_value('display.action_bubble_bg_color')
    ACTION_BUBBLE_TEXT_COLOR = config.get_value('display.action_bubble_text_color')

    return f"""
QWidget {{
    background-color: {PRIMARY_COLOR};
    border-radius: 12px;
}}
QTextEdit {{
    background-color: {SECONDARY_COLOR};
    border-radius: 12px;
    color: #FFF;
    padding-left: 5px;
}}
QTextEdit.msgbox {{
    background-color: {SECONDARY_COLOR};
    border-radius: 12px;
    border-top-right-radius: 0px;
    border-bottom-right-radius: 0px;
    font-size: {TEXT_SIZE}px; 
}}
QPushButton.resend {{
    background-color: none;
    border-radius: 12px;
}}
QPushButton.resend:hover {{
    background-color: #777;
    border-radius: 12px;
}}
QPushButton.rerun {{
    background-color: {CODE_BUBBLE_BG_COLOR};
    border-radius: 12px;
}}
QPushButton.send {{
    background-color: {SECONDARY_COLOR};
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    border-top-left-radius: 0px;
    border-bottom-left-radius: 0px;
    color: {TEXT_COLOR};
}}
QPushButton:hover {{
    background-color: #444;
}}
QPushButton.send:hover {{
    background-color: #537373;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    border-top-left-radius: 0px;
    border-bottom-left-radius: 0px;
    color: {TEXT_COLOR};
}}
QPushButton {{
    color: {TEXT_COLOR};
    border-radius: 3px;
}}
QPushButton.menuitem {{
    color: {TEXT_COLOR};
    border-radius: 3px;
}}
QPushButton#homebutton:checked {{
    background-color: none;
    color: {TEXT_COLOR};
}}
QPushButton#homebutton:checked:hover {{
    background-color: #444;
    color: {TEXT_COLOR};
}}
QPushButton:checked {{
    background-color: #444;
    border-radius: 3px;
}}
QPushButton:checked:hover {{
    background-color: #444;
    border-radius: 3px;
}}
QLineEdit {{
    color: {TEXT_COLOR};
}}
QLineEdit:disabled {{
    color: #4d4d4d;
}}
QLabel {{
    color: {TEXT_COLOR};
    padding-right: 10px; 
}}
QSpinBox {{
    color: {TEXT_COLOR};
}}
QCheckBox::indicator:unchecked {{
    border: 1px solid #2b2b2b;
    background: {TEXT_COLOR};
}}
QCheckBox::indicator:checked {{
    border: 1px solid #2b2b2b;
    background: {TEXT_COLOR} url("./utils/resources/icon-tick.svg") no-repeat center center;
}}
QCheckBox::indicator:unchecked:disabled {{
    border: 1px solid #2b2b2b;
    background: #424242;
}}
QCheckBox::indicator:checked:disabled {{
    border: 1px solid #2b2b2b;
    background: #424242;
}}
QWidget.central {{
    border-radius: 12px;
    border-top-left-radius: 30px;
}}
QTextEdit.user {{
    background-color: {USER_BUBBLE_BG_COLOR};
    color: {USER_BUBBLE_TEXT_COLOR};
    font-size: {TEXT_SIZE}px; 
    border-radius: 12px;
    border-bottom-left-radius: 0px;
    /* border-top-right-radius: 0px;*/
}}
QTextEdit.assistant {{
    background-color: {ASSISTANT_BUBBLE_BG_COLOR};
    color: {ASSISTANT_BUBBLE_TEXT_COLOR};
    font-size: {TEXT_SIZE}px; 
    border-radius: 12px;
    border-bottom-left-radius: 0px;
    /* border-top-right-radius: 0px;*/
}}
QTextEdit.code {{
    background-color: {CODE_BUBBLE_BG_COLOR};
    color: {CODE_BUBBLE_TEXT_COLOR};
    font-size: {TEXT_SIZE}px; 
}}
QScrollBar:vertical {{
    width: 0px;
}}
"""

class TitleButtonBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.main = parent
        self.setObjectName("TitleBarWidget")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(20)
        sizePolicy = QSizePolicy()
        sizePolicy.setHorizontalPolicy(QSizePolicy.Policy.Fixed)

        self.btn_minimise = self.TitleBarButtonMin(parent=self)
        self.btn_pin = self.TitleBarButtonPin(parent=self)
        self.btn_close = self.TitleBarButtonClose(parent=self)

        self.layout = QHBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addStretch(1)
        self.layout.addWidget(self.btn_minimise)
        self.layout.addWidget(self.btn_pin)
        self.layout.addWidget(self.btn_close)

        self.setMouseTracking(True)

        self.setAttribute(Qt.WA_TranslucentBackground, True)

    class TitleBarButtonPin(QPushButton):
        def __init__(self, parent=None):
            super().__init__(parent=parent)
            self.setFixedHeight(20)
            self.setFixedWidth(20)
            self.clicked.connect(self.toggle_pin)
            self.icon = QIcon(QPixmap("./utils/resources/icon-pin-on.png"))
            self.setIcon(self.icon)

        def toggle_pin(self):
            global PIN_STATE
            PIN_STATE = not PIN_STATE
            icon_iden = "on" if PIN_STATE else "off"
            icon_file = f"./utils/resources/icon-pin-{icon_iden}.png"
            self.icon = QIcon(QPixmap(icon_file))
            self.setIcon(self.icon)

    class TitleBarButtonMin(QPushButton):
        def __init__(self, parent=None):
            super().__init__(parent=parent)
            self.parent = parent
            self.setFixedHeight(20)
            self.setFixedWidth(20)
            self.clicked.connect(self.window_action)
            self.icon = QIcon(QPixmap("./utils/resources/minus.png"))
            self.setIcon(self.icon)

        def window_action(self):
            self.parent.main.collapse()
            if self.window().isMinimized():
                self.window().showNormal()
            else:
                self.window().showMinimized()

    class TitleBarButtonClose(QPushButton):

        def __init__(self, parent):
            super().__init__(parent=parent)
            self.setFixedHeight(20)
            self.setFixedWidth(20)
            self.clicked.connect(self.closeApp)
            self.icon = QIcon(QPixmap("./utils/resources/close.png"))
            self.setIcon(self.icon)

        def closeApp(self):
            self.parent().main.window().close()
            # self.window().close()
            # sys.exit()


class ContentPage(QWidget):
    def __init__(self, main, title=''):
        super().__init__(parent=main)

        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.back_button = Back_Button(main)
        self.label = QLabel(title)

        font = self.label.font()
        font.setPointSize(15)
        self.label.setFont(font)
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

class BaseTableWidget(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.verticalHeader().setVisible(False)
        # self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.setSortingEnabled(True)
        # self.setMouseTracking(True)
        # self.setContextMenuPolicy(Qt.CustomContextMenu)
        # self.customContextMenuRequested.connect(self.open_menu)
        self.setShowGrid(False)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setColumnHidden(0, True)

        palette = self.palette()
        palette.setColor(QPalette.Highlight, QColor(SECONDARY_COLOR))  # Setting it to red
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))  # Setting text color to white
        palette.setColor(QPalette.Text, QColor(TEXT_COLOR))  # Setting unselected text color to purple
        self.setPalette(palette)


class ColorPickerButton(QPushButton):
    colorChanged = Signal(str)  # Define a new signal that passes a string

    def __init__(self):
        super().__init__()
        self.color = None
        self.setFixedSize(24, 24)  # Or any other appropriate size for your square
        self.setStyleSheet("background-color: white; border: none;")  # Default color and style
        self.clicked.connect(self.pick_color)

    def pick_color(self):
        global PIN_STATE
        current_pin_state = PIN_STATE
        PIN_STATE = True

        current_color = self.color if self.color else Qt.white
        color = QColorDialog.getColor(current_color, self)

        if color.isValid():
            self.color = color
            self.setStyleSheet(f"background-color: {color.name()}; border: none;")
            self.colorChanged.emit(color.name())  # Emit the signal with the new color name

        PIN_STATE = current_pin_state

    def set_color(self, hex_color):
        color = QColor(hex_color)
        if color.isValid():
            self.color = color
            self.setStyleSheet(f"background-color: {color.name()}; border: none;")

    def get_color(self):
        return self.color.name() if self.color and self.color.isValid() else None
# class ColorPickerButton(QPushButton):
#     colorChanged = Signal(str)  # Define a new signal that passes a string
#     def __init__(self, title=''):
#         super().__init__(title)
#         self.color = None
#         self.clicked.connect(self.pick_color)
#
#     def pick_color(self):
#         global PIN_STATE
#         current_pin_state = PIN_STATE
#         PIN_STATE = True
#
#         current_color = self.color if self.color else Qt.white
#         self.color = QColorDialog.getColor(current_color, self)
#
#         if self.color.isValid():
#             self.setStyleSheet(f"background-color: {self.color.name()}")
#             self.colorChanged.emit(self.color.name())  # Emit the signal with the new color name
#
#         PIN_STATE = current_pin_state
#
#     def get_color(self):
#         return self.color.name() if self.color else None
#
#     def set_color(self, hex_color):
#         self.color = hex_color
#         self.setStyleSheet(f"background-color: {self.color}")


class CComboBox(QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        global PIN_STATE
        self.current_pin_state = PIN_STATE

        self.setFixedWidth(150)
        # number_of_items_to_show = 5
        # item_height = self.view().sizeHintForRow(20)  # Height of a single item
        # dropdown_height = item_height * number_of_items_to_show
        #
        # # Set the fixed height for the dropdown item list
        # self.view().setFixedHeight(dropdown_height)
        # # Ensure the vertical scrollbar appears if there are more items than the fixed height can display
        # self.view().setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def showPopup(self):
        global PIN_STATE
        self.current_pin_state = PIN_STATE
        PIN_STATE = True
        super().showPopup()  # Call the base class method to ensure the popup is shown

    def hidePopup(self):
        global PIN_STATE
        super().hidePopup()  # Call the base class method to ensure the popup is shown
        PIN_STATE = self.current_pin_state

class PluginComboBox(CComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setItemDelegate(AlignDelegate(self))
        self.setStyleSheet("QComboBox::drop-down {border-width: 0px;} QComboBox::down-arrow {image: url(noimg); border-width: 0px;}")
        self.load()

    def load(self):
        # clear items
        self.clear()
        self.addItem("Choose Plugin", "")
        self.addItem("Mem GPT", "memgpt")
        self.addItem("Open Interpreter", "openinterpreter")

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
        # Adjust the rectangle to shift text 20 pixels to the left
        text_rect.adjust(18, 0, 0, 0)  # left, top, right, bottom

        current_text = self.currentText()
        painter.drawText(text_rect, Qt.AlignCenter, current_text)



class ModelComboBox(CComboBox):
    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)

        self.load()

    def load(self):
        # clear items
        self.clear()
        models = sql.get_results("SELECT name, model_name FROM models")
        if self.first_item:
            self.addItem(self.first_item, 0)
        for model in models:
            self.addItem(model[0], model[1])


class APIComboBox(CComboBox):
    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)

        self.load()

    def load(self):
        # clear items
        self.clear()
        models = sql.get_results("SELECT name, id FROM apis")
        if self.first_item:
            self.addItem(self.first_item, 0)
        # self.addItem('LOCAL', 0)
        for model in models:
            self.addItem(model[0], model[1])


class AlignDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        option.displayAlignment = Qt.AlignCenter
        super(AlignDelegate, self).paint(painter, option, index)


# class CustomScrollArea(QScrollArea):
#     def __init__(self, parent=None):
#         super().__init__(parent)
#         self.parent = parent


class Back_Button(QPushButton):
    def __init__(self, main):
        super().__init__(parent=main, icon=QIcon())
        self.main = main
        self.clicked.connect(self.go_back)
        self.icon = QIcon(QPixmap("./utils/resources/icon-back.png"))
        self.setIcon(self.icon)
        self.setFixedSize(50, 50)
        self.setIconSize(QSize(50, 50))

    def go_back(self):
        self.main.content.setCurrentWidget(self.main.page_chat)
        self.main.sidebar.btn_new_context.setChecked(True)


class Page_Settings(ContentPage):
    def __init__(self, main):
        super().__init__(main=main, title='Settings')
        self.main = main

        self.settings_sidebar = self.Settings_SideBar(main=main, parent=self)

        self.content = QStackedWidget(self)
        self.page_system = self.Page_System_Settings(self)
        self.page_api = self.Page_API_Settings(self)
        self.page_display = self.Page_Display_Settings(self)
        self.page_block = self.Page_Block_Settings(self)
        self.page_models = self.Page_Model_Settings(self)
        self.content.addWidget(self.page_system)
        self.content.addWidget(self.page_api)
        self.content.addWidget(self.page_display)
        self.content.addWidget(self.page_block)
        self.content.addWidget(self.page_models)

        # H layout for lsidebar and content
        input_layout = QHBoxLayout()
        input_layout.addWidget(self.settings_sidebar)
        input_layout.addWidget(self.content)
        # input_layout.addLayout(self.form_layout)

        # Create a QWidget to act as a container for the
        input_container = QWidget()
        input_container.setLayout(input_layout)

        # Adding input layout to the main layout
        self.layout.addWidget(input_container)

        self.layout.addStretch(1)

    def load(self):  # Load Settings
        # self.settings_sidebar.updateButtonStates()
        self.content.currentWidget().load()

    def update_config(self, key, value):
        config.set_value(key, value)
        config.load_config()
        self.main.set_stylesheet()
        self.main.page_chat.load_bubbles()

    class Settings_SideBar(QWidget):
        def __init__(self, main, parent):
            super().__init__(parent=main)
            self.main = main
            self.parent = parent
            self.setObjectName("SettingsSideBarWidget")
            self.setAttribute(Qt.WA_StyledBackground, True)
            self.setProperty("class", "sidebar")

            font = QFont()
            font.setPointSize(13)  # Set font size to 20 points

            self.btn_system = self.Settings_SideBar_Button(main=main, text='System')
            self.btn_system.setFont(font)
            self.btn_system.setChecked(True)
            self.btn_api = self.Settings_SideBar_Button(main=main, text='API')
            self.btn_api.setFont(font)
            self.btn_display = self.Settings_SideBar_Button(main=main, text='Display')
            self.btn_display.setFont(font)
            self.btn_blocks = self.Settings_SideBar_Button(main=main, text='Blocks')
            self.btn_blocks.setFont(font)
            self.btn_models = self.Settings_SideBar_Button(main=main, text='Models')
            self.btn_models.setFont(font)

            self.layout = QVBoxLayout(self)
            self.layout.setSpacing(0)
            self.layout.setContentsMargins(0, 0, 0, 0)

            # Create a button group and add buttons to it
            self.button_group = QButtonGroup(self)
            self.button_group.addButton(self.btn_system, 0)  # 0 is the ID associated with the button
            self.button_group.addButton(self.btn_api, 1)
            self.button_group.addButton(self.btn_display, 2)
            self.button_group.addButton(self.btn_blocks, 3)
            self.button_group.addButton(self.btn_models, 4)

            # Connect button toggled signal
            self.button_group.buttonToggled[QAbstractButton, bool].connect(self.onButtonToggled)

            # self.layout.addStretch(1)

            self.layout.addWidget(self.btn_system)
            self.layout.addWidget(self.btn_api)
            self.layout.addWidget(self.btn_display)
            self.layout.addWidget(self.btn_blocks)
            self.layout.addWidget(self.btn_models)
            self.layout.addStretch(1)

        def onButtonToggled(self, button, checked):
            if checked:
                index = self.button_group.id(button)
                self.parent.content.setCurrentIndex(index)
                self.parent.content.currentWidget().load()

        def updateButtonStates(self):
            # Check the appropriate button based on the current page
            stacked_widget = self.parent.content
            self.btn_system.setChecked(stacked_widget.currentWidget() == self.btn_system)
            self.btn_api.setChecked(stacked_widget.currentWidget() == self.btn_api)

        class Settings_SideBar_Button(QPushButton):
            def __init__(self, main, text=''):
                super().__init__(parent=main, icon=QIcon())
                self.main = main
                self.setProperty("class", "menuitem")
                self.setText(text)
                self.setFixedSize(100, 25)
                self.setCheckable(True)

    class Page_System_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.form_layout = QFormLayout()

            #text field for dbpath
            self.db_path = QLineEdit()
            self.form_layout.addRow(QLabel('Database Path:'), self.db_path)

            self.setLayout(self.form_layout)

        def load(self):
            # config = self.parent.main.page_chat.agent.config
            with block_signals(self):
                self.db_path.setText(config.get_value('system.db_path'))

    class Page_Display_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.form_layout = QFormLayout()

            # Primary Color
            self.primary_color_picker = ColorPickerButton()
            self.form_layout.addRow(QLabel('Primary Color:'), self.primary_color_picker)
            self.primary_color_picker.colorChanged.connect(lambda color: self.parent.update_config('display.primary_color', color))

            # Secondary Color
            self.secondary_color_picker = ColorPickerButton()
            self.form_layout.addRow(QLabel('Secondary Color:'), self.secondary_color_picker)
            self.secondary_color_picker.colorChanged.connect(lambda color: self.parent.update_config('display.secondary_color', color))

            # Text Color
            self.text_color_picker = ColorPickerButton()
            self.form_layout.addRow(QLabel('Text Color:'), self.text_color_picker)
            self.text_color_picker.colorChanged.connect(lambda color: self.parent.update_config('display.text_color', color))

            # Text Font (dummy data)
            self.text_font_dropdown = CComboBox()
            font_database = QFontDatabase()
            available_fonts = font_database.families()
            self.text_font_dropdown.addItems(available_fonts)

            font_delegate = self.FontItemDelegate(self.text_font_dropdown)
            self.text_font_dropdown.setItemDelegate(font_delegate)
            self.form_layout.addRow(QLabel('Text Font:'), self.text_font_dropdown)
            self.text_font_dropdown.currentTextChanged.connect(lambda font: self.parent.update_config('display.text_font', font))

            # Text Size
            self.text_size_input = QSpinBox()
            self.text_size_input.setRange(6, 72)  # Assuming a reasonable range for font sizes
            self.form_layout.addRow(QLabel('Text Size:'), self.text_size_input)
            self.text_size_input.valueChanged.connect(lambda size: self.parent.update_config('display.text_size', size))

            # Other color settings
            self.user_bubble_bg_color_picker = ColorPickerButton()
            self.form_layout.addRow(QLabel('User Bubble Background Color:'), self.user_bubble_bg_color_picker)
            self.user_bubble_bg_color_picker.colorChanged.connect(lambda color: self.parent.update_config('display.user_bubble_bg_color', color))

            self.user_bubble_text_color_picker = ColorPickerButton()
            self.form_layout.addRow(QLabel('User Bubble Text Color:'), self.user_bubble_text_color_picker)
            self.user_bubble_text_color_picker.colorChanged.connect(lambda color: self.parent.update_config('display.user_bubble_text_color', color))

            self.assistant_bubble_bg_color_picker = ColorPickerButton()
            self.form_layout.addRow(QLabel('Assistant Bubble Background Color:'), self.assistant_bubble_bg_color_picker)
            self.assistant_bubble_bg_color_picker.colorChanged.connect(lambda color: self.parent.update_config('display.assistant_bubble_bg_color', color))

            self.assistant_bubble_text_color_picker = ColorPickerButton()
            self.form_layout.addRow(QLabel('Assistant Bubble Text Color:'), self.assistant_bubble_text_color_picker)
            self.assistant_bubble_text_color_picker.colorChanged.connect(lambda color: self.parent.update_config('display.assistant_bubble_text_color', color))

            self.code_bubble_bg_color_picker = ColorPickerButton()
            self.form_layout.addRow(QLabel('Code Bubble Background Color:'), self.code_bubble_bg_color_picker)
            self.code_bubble_bg_color_picker.colorChanged.connect(lambda color: self.parent.update_config('display.code_bubble_bg_color', color))

            self.code_bubble_text_color_picker = ColorPickerButton()
            self.form_layout.addRow(QLabel('Code Bubble Text Color:'), self.code_bubble_text_color_picker)
            self.code_bubble_text_color_picker.colorChanged.connect(lambda color: self.parent.update_config('display.code_bubble_text_color', color))

            self.action_bubble_bg_color_picker = ColorPickerButton()
            self.form_layout.addRow(QLabel('Action Bubble Background Color:'), self.action_bubble_bg_color_picker)
            self.action_bubble_bg_color_picker.colorChanged.connect(lambda color: self.parent.update_config('display.action_bubble_bg_color', color))

            self.action_bubble_text_color_picker = ColorPickerButton()
            self.form_layout.addRow(QLabel('Action Bubble Text Color:'), self.action_bubble_text_color_picker)
            self.action_bubble_text_color_picker.colorChanged.connect(lambda color: self.parent.update_config('display.action_bubble_text_color', color))

            self.setLayout(self.form_layout)
            self.load()

        def load(self):
            # Implement your loading logic here
            # For example, if you have config data, you might do something like:
            # config = self.parent.main.page_chat.agent.config
            with block_signals(self):
                self.primary_color_picker.set_color(config.get_value('display.primary_color'))
                self.secondary_color_picker.set_color(config.get_value('display.secondary_color'))
                self.text_color_picker.set_color(config.get_value('display.text_color'))
                self.user_bubble_bg_color_picker.set_color(config.get_value('display.user_bubble_bg_color'))
                self.user_bubble_text_color_picker.set_color(config.get_value('display.user_bubble_text_color'))
                self.assistant_bubble_bg_color_picker.set_color(config.get_value('display.assistant_bubble_bg_color'))
                self.assistant_bubble_text_color_picker.set_color(config.get_value('display.assistant_bubble_text_color'))
                self.code_bubble_bg_color_picker.set_color(config.get_value('display.code_bubble_bg_color'))
                self.code_bubble_text_color_picker.set_color(config.get_value('display.code_bubble_text_color'))
                self.action_bubble_bg_color_picker.set_color(config.get_value('display.action_bubble_bg_color'))
                self.action_bubble_text_color_picker.set_color(config.get_value('display.action_bubble_text_color'))
                self.text_font_dropdown.setCurrentText(config.get_value('display.text_font'))
                self.text_size_input.setValue(config.get_value('display.text_size'))

        class FontItemDelegate(QStyledItemDelegate):
            def paint(self, painter, option, index):
                # Get the font name from the current item
                font_name = index.data()

                # Create a QFont object using the font name
                font = QFont(font_name)

                # Set the font size to a default value for display purposes (optional)
                font.setPointSize(12)  # for example, size 12

                # Set the font for the painter and then draw the text
                painter.setFont(font)
                painter.drawText(option.rect, index.data())

            def sizeHint(self, option, index):
                # You might want to provide a custom size hint to ensure adequate space
                # for each font, especially if they have varying glyph sizes.
                return super().sizeHint(option, index)

    class Page_API_Settings(QWidget):
        def __init__(self, main):
            super().__init__(parent=main)

            self.layout = QVBoxLayout(self)

            self.table = BaseTableWidget(self)
            self.table.setColumnCount(4)
            self.table.setColumnHidden(0, True)
            self.table.setHorizontalHeaderLabels(['ID', 'Name', 'Client Key', 'Private Key'])
            self.table.horizontalHeader().setStretchLastSection(True)
            self.table.itemChanged.connect(self.item_edited)  # Connect the itemChanged signal to the item_edited method

            # Additional attribute to store the locked status of each API
            self.api_locked_status = {}

            self.layout.addWidget(self.table)

            # Buttons
            self.add_button = QPushButton("Add", self)
            self.add_button.clicked.connect(self.add_entry)

            self.delete_button = QPushButton("Delete", self)
            self.delete_button.clicked.connect(self.delete_entry)

            self.button_layout = QHBoxLayout()
            self.button_layout.addWidget(self.add_button)
            self.button_layout.addWidget(self.delete_button)
            self.layout.addLayout(self.button_layout)

            self.setLayout(self.layout)

            # self.load_data()

        def load(self):
            # Fetch the data from the database
            self.table.blockSignals(True)
            self.table.setRowCount(0)
            data = sql.get_results("""
                SELECT
                    id,
                    name,
                    client_key,
                    priv_key,
                    locked
                FROM apis""")
            for row_data in data:
                row_position = self.table.rowCount()
                self.table.insertRow(row_position)
                # api_id = None
                for column, item in enumerate(row_data):
                    # is_locked = row_data[4]
                    if column == 0:
                        api_id = item
                    if column < 4:  # Ensure we only add the first four items to the table
                        self.table.setItem(row_position, column, QTableWidgetItem(str(item)))
                # Store the 'locked' status
                # self.api_locked_status[api_id] = is_locked
                # set name column to read only if is_locked
                # if is_locked:
                #     self.table.item(row_position, 1).setFlags(Qt.ItemIsEnabled)
            self.table.blockSignals(False)

        def item_edited(self, item):
            # Proceed with updating the database
            row = item.row()
            api_id = self.table.item(row, 0).text()

            # # Check if the API is locked
            # if self.api_locked_status.get(int(api_id)):
            #     QMessageBox.warning(self, "Locked API", "This API is locked and cannot be edited.")
            #     return

            id_map = {
                2: 'client_key',
                3: 'priv_key'
            }

            column = item.column()
            if column not in id_map:
                return
            column_name = id_map.get(column)
            new_value = item.text()
            sql.execute(f"""
                UPDATE apis
                SET {column_name} = ?
                WHERE id = ?
            """, (new_value, api_id,))

            # reload api settings
            api.load_api_keys()

        def delete_entry(self):
            current_row = self.table.currentRow()
            if current_row == -1:
                return

            api_id = self.table.item(current_row, 0).text()
            # Check if the API is locked
            if self.api_locked_status.get(int(api_id)):
                QMessageBox.warning(self, "Locked API", "This API is locked and cannot be deleted.")
                return

            # Proceed with deletion from the database and the table
            pass
        def add_entry(self):
            pass

    class Page_Block_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.layout = QHBoxLayout(self)

            self.table = BaseTableWidget(self)
            self.table.setColumnCount(2)
            self.table.setColumnHidden(0, True)
            self.table.setHorizontalHeaderLabels(['ID', 'Name'])
            self.table.horizontalHeader().setStretchLastSection(True)
            self.table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
            self.table.itemChanged.connect(self.name_edited)  # Connect the itemChanged signal to the item_edited method
            self.table.itemSelectionChanged.connect(self.on_block_selected)

            # self.table.setColumnWidth(1, 125)  # Set Name column width

            # Adding table to the layout
            self.layout.addWidget(self.table)

            # block data area
            self.block_data_layout = QVBoxLayout()
            self.block_data_label = QLabel("Block data")
            self.block_data_text_area = QTextEdit()
            self.block_data_text_area.textChanged.connect(self.text_edited)

            # Adding widgets to the vertical layout
            self.block_data_layout.addWidget(self.block_data_label)
            self.block_data_layout.addWidget(self.block_data_text_area)

            # Adding the vertical layout to the main layout
            self.layout.addLayout(self.block_data_layout)

        def load(self):
            # Fetch the data from the database
            self.table.blockSignals(True)
            self.table.setRowCount(0)
            data = sql.get_results("""
                SELECT
                    id,
                    name
                FROM blocks""")
            for row_data in data:
                row_position = self.table.rowCount()
                self.table.insertRow(row_position)
                for column, item in enumerate(row_data):
                    self.table.setItem(row_position, column, QTableWidgetItem(str(item)))
            self.table.blockSignals(False)

            if self.table.rowCount() > 0:
                self.table.selectRow(0)

        def name_edited(self, item):
            row = item.row()
            if row == -1: return
            block_id = self.table.item(row, 0).text()

            id_map = {
                1: 'name',
            }

            column = item.column()
            if column not in id_map:
                return
            column_name = id_map.get(column)
            new_value = item.text()
            sql.execute(f"""
                UPDATE blocks
                SET {column_name} = ?
                WHERE id = ?
            """, (new_value, block_id,))

            # reload blocks
            self.parent.main.page_chat.agent.load_agent()

        def text_edited(self):
            current_row = self.table.currentRow()
            if current_row == -1: return
            block_id = self.table.item(current_row, 0).text()
            text = self.block_data_text_area.toPlainText()
            sql.execute(f"""
                UPDATE blocks
                SET text = ?
                WHERE id = ?
            """, (text, block_id,))

            # reload blocks
            self.parent.main.page_chat.agent.load_agent()

        def on_block_selected(self):
            current_row = self.table.currentRow()
            if current_row == -1: return
            att_id = self.table.item(current_row, 0).text()
            att_text = sql.get_scalar(f"""
                SELECT
                    `text`
                FROM blocks
                WHERE id = ?
            """, (att_id,))
            self.block_data_text_area.setText(att_text)

    class Page_Model_Settings(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent=parent)
            self.parent = parent

            # Main layout
            self.layout = QHBoxLayout(self)

            # Side panel
            self.side_panel = QWidget(self)
            self.side_panel_layout = QVBoxLayout(self.side_panel)

            # Create a horizontal layout for the combo box and new model button
            self.combo_button_layout = QHBoxLayout()
            self.side_panel_layout.addLayout(self.combo_button_layout)

            # APIComboBox
            self.api_combo_box = APIComboBox(self, first_item='LOCAL')
            self.api_combo_box.currentIndexChanged.connect(self.on_api_changed)
            self.combo_button_layout.addWidget(self.api_combo_box)

            # Spacer item
            spacer = QWidget(self)
            spacer.setFixedSize(30, 1)  # 30px wide spacer, height doesn't matter
            self.combo_button_layout.addWidget(spacer)

            # New Model button
            self.new_model_button = self.Button_New_Model(self)
            self.combo_button_layout.addWidget(self.new_model_button)

            # New Model button
            self.del_model_button = self.Button_Delete_Model(self)
            self.combo_button_layout.addWidget(self.del_model_button)

            # Models list
            self.models_label = QLabel("Models:")
            self.models_list = QListWidget(self)
            self.models_list.setSelectionMode(QListWidget.SingleSelection)
            self.models_list.currentItemChanged.connect(self.on_model_selected)

            self.side_panel_layout.addWidget(self.models_label)
            self.side_panel_layout.addWidget(self.models_list, stretch=1)

            # Adding side panel to main layout
            self.layout.addWidget(self.side_panel)

            # Placeholder for main content
            self.main_content = QWidget(self)
            self.main_content_layout = QVBoxLayout(self.main_content)
            # Add other main content widgets here as needed

            self.layout.addWidget(self.main_content, stretch=1)

        class Button_New_Model(QPushButton):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent
                self.clicked.connect(self.new_model)
                self.icon = QIcon(QPixmap("./utils/resources/icon-new.png"))  # Path to your icon
                self.setIcon(self.icon)
                self.setFixedSize(25, 25)  # Adjust the size as needed
                self.setIconSize(QSize(25, 25))  # The size of the icon

            def new_model(self):
                global PIN_STATE
                current_pin_state = PIN_STATE
                PIN_STATE = True
                text, ok = QInputDialog.getText(self, 'New Model', 'Enter a name for the model:')

                # Check if the OK button was clicked
                if ok and text:
                    # Logic for creating a new model in the database
                    sql.execute("INSERT INTO `models` (`name`, `api_id`, `model_name`) VALUES (?, ?, '')", (text, self.parent.api_combo_box.currentData(),))
                    self.parent.load_models()  # Reload the list of models
                PIN_STATE = current_pin_state

        class Button_Delete_Model(QPushButton):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent
                self.clicked.connect(self.delete_model)
                self.icon = QIcon(QPixmap("./utils/resources/icon-delete.png"))  # Path to your icon
                self.setIcon(self.icon)
                self.setFixedSize(25, 25)  # Adjust the size as needed
                self.setIconSize(QSize(25, 25))  # The size of the icon

            def delete_model(self):
                global PIN_STATE

                current_item = self.parent.models_list.currentItem()
                if current_item is None:
                    return

                msg = QMessageBox()
                msg.setIcon(QMessageBox.Warning)
                msg.setText(f"Are you sure you want to delete this model?")
                msg.setWindowTitle("Delete Model")
                msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

                current_pin_state = PIN_STATE
                PIN_STATE = True
                retval = msg.exec_()
                PIN_STATE = current_pin_state
                if retval != QMessageBox.Yes:
                    return

                # Logic for deleting a model from the database
                current_model_id = current_item.data(Qt.UserRole)
                sql.execute("DELETE FROM `models` WHERE `id` = ?", (current_model_id,))
                self.parent.load_models()  # Reload the list of models

        def load_models(self):
            # Clear the current items in the list
            self.models_list.clear()

            # Get the currently selected API's ID
            current_api_id = self.api_combo_box.currentData()

            # Fetch the models from the database
            data = sql.get_results("SELECT id, name FROM models WHERE api_id = ?", (current_api_id,))
            for row_data in data:
                # Assuming row_data structure: (id, name)
                model_id, model_name = row_data

                # Create a QListWidgetItem with the model's name
                item = QListWidgetItem(model_name)

                # Store the model's ID as custom data (UserRole) within the item
                item.setData(Qt.UserRole, model_id)

                # Add the item to the models list
                self.models_list.addItem(item)

            # Select the first model in the list by default
            if self.models_list.count() > 0:
                self.models_list.setCurrentRow(0)

        def load(self):
            # Fetch and load APIs into the APIComboBox
            self.api_combo_box.load()  # Assuming the APIComboBox has a load method to fetch data
            self.load_models()  # Load models based on the selected API

        def on_api_changed(self, index):
            # This method is called whenever the selected item of the APIComboBox changes
            self.load_models()

        def on_model_selected(self, current, previous):
            # This method is called whenever a model is selected from the list
            if current:
                model_name = current.text()
                # Here you can handle what happens when a model is selected
                # For example, you can fetch more data from the database and display it in the main content area
                pass  # Your logic goes here

    # class Page_Model_Settings(QWidget):
    #     def __init__(self, parent=None):
    #         super().__init__(parent=parent)
    #         self.parent = parent
    #
    #         # Main layout
    #         self.layout = QHBoxLayout(self)
    #
    #         # Side panel
    #         self.side_panel = QWidget(self)
    #         self.side_panel_layout = QVBoxLayout(self.side_panel)
    #
    #         # APIComboBox
    #         self.api_combo_box = APIComboBox(self)
    #         self.side_panel_layout.addWidget(self.api_combo_box)
    #
    #         # Models list
    #         self.models_label = QLabel("Models:")
    #         self.models_list = QListWidget(self)
    #         self.models_list.setSelectionMode(QListWidget.SingleSelection)
    #         self.models_list.currentItemChanged.connect(self.on_model_selected)
    #
    #         self.side_panel_layout.addWidget(self.models_label)
    #         self.side_panel_layout.addWidget(self.models_list, stretch=1)
    #
    #         # Adding side panel to main layout
    #         self.layout.addWidget(self.side_panel)
    #
    #         # Placeholder for main content
    #         self.main_content = QWidget(self)
    #         self.main_content_layout = QVBoxLayout(self.main_content)
    #         # Add other main content widgets here as needed
    #
    #         self.layout.addWidget(self.main_content, stretch=1)
    #
    #     def load(self):
    #         # Clear the current items in the list
    #         self.models_list.clear()
    #
    #         # Fetch and load APIs into the APIComboBox
    #         self.api_combo_box.load()  # Assuming the APIComboBox has a load method to fetch data
    #
    #         # Fetch the models from the database
    #         data = sql.get_results("SELECT id, name FROM models")
    #         for row_data in data:
    #             # Assuming row_data structure: (id, name)
    #             model_id, model_name = row_data
    #             # Adding the model name to the list widget; you can use model_id as needed
    #             self.models_list.addItem(model_name)
    #
    #         # Select the first model in the list by default
    #         if self.models_list.count() > 0:
    #             self.models_list.setCurrentRow(0)
    #
    #     def on_model_selected(self, current, previous):
    #         # This method is called whenever a model is selected from the list
    #         if current:
    #             model_name = current.text()
    #             # Here you can handle what happens when a model is selected
    #             # For example, you can fetch more data from the database and display it in the main content area
    #             pass  # Your logic goes here


class Page_Agents(ContentPage):
    def __init__(self, main):
        super().__init__(main=main, title='Agents')
        self.main = main

        self.settings_sidebar = self.Agent_Settings_SideBar(main=main, parent=self)

        self.agent_id = 0
        self.agent_config = {}

        self.content = QStackedWidget(self)
        self.page_general = self.Page_General_Settings(self)
        self.page_context = self.Page_Context_Settings(self)
        self.page_actions = self.Page_Actions_Settings(self)
        # self.page_code = self.Page_Plugins_Settings(self)
        self.page_voice = self.Page_Voice_Settings(self)
        self.content.addWidget(self.page_general)
        self.content.addWidget(self.page_context)
        self.content.addWidget(self.page_actions)
        # self.content.addWidget(self.page_code)
        self.content.addWidget(self.page_voice)

        # H layout for lsidebar and content
        input_layout = QHBoxLayout()
        input_layout.addWidget(self.settings_sidebar)
        input_layout.addWidget(self.content)

        # Create a QWidget to act as a container for the
        input_container = QWidget()
        input_container.setLayout(input_layout)

        # add button to title widget

        self.btn_new_agent = self.Button_New_Agent(parent=self)
        self.title_layout.addWidget(self.btn_new_agent)  # QPushButton("Add", self))

        self.title_layout.addStretch()

        # Adding input layout to the main layout
        self.table_widget = BaseTableWidget(self)
        self.table_widget.setColumnCount(6)
        self.table_widget.setColumnWidth(1, 45)
        self.table_widget.setColumnWidth(4, 45)
        self.table_widget.setColumnWidth(5, 45)
        self.table_widget.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table_widget.hideColumn(0)
        self.table_widget.hideColumn(2)
        self.table_widget.horizontalHeader().hide()
        self.table_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_widget.itemSelectionChanged.connect(self.on_agent_selected)

        # self.load_agents()
        # Add the table to the layout
        self.layout.addWidget(self.table_widget)
        self.layout.addWidget(input_container)

    def load(self):  # Load agents
        icon_chat = QIcon('./utils/resources/icon-chat.png')
        icon_del = QIcon('./utils/resources/icon-delete.png')

        with block_signals(self):
            self.table_widget.setRowCount(0)
            data = sql.get_results("""
                SELECT
                    id,
                    '' AS avatar,
                    config,
                    name,
                    '' AS chat_button,
                    '' AS del_button
                FROM agents
                ORDER BY id DESC""")
            for row_data in data:
                row_position = self.table_widget.rowCount()
                self.table_widget.insertRow(row_position)
                for column, item in enumerate(row_data):
                    self.table_widget.setItem(row_position, column, QTableWidgetItem(str(item)))

                # Parse the config JSON to get the avatar path
                config = json.loads(row_data[2])  # Assuming config is the second column and in JSON format
                agent_avatar_path = config.get('general.avatar_path', '')

                # Create the circular avatar QPixmap
                try:
                    if agent_avatar_path == '':
                        raise Exception('No avatar path')
                    avatar_img = QPixmap(agent_avatar_path)
                except Exception as e:
                    avatar_img = QPixmap("./utils/resources/icon-agent.png")

                circular_avatar_pixmap = create_circular_pixmap(avatar_img, diameter=25)

                # Create a QLabel to hold the pixmap
                avatar_label = QLabel()
                avatar_label.setPixmap(circular_avatar_pixmap)
                # set background to transparent
                avatar_label.setAttribute(Qt.WA_TranslucentBackground, True)

                # Add the new avatar icon column after the ID column
                self.table_widget.setCellWidget(row_position, 1, avatar_label)

                # set btn icon
                btn_chat = QPushButton('')
                btn_chat.setIcon(icon_chat)
                btn_chat.setIconSize(QSize(25, 25))
                btn_chat.clicked.connect(partial(self.chat_with_agent, row_data))
                self.table_widget.setCellWidget(row_position, 4, btn_chat)

                # set btn icon
                btn_del = QPushButton('')
                btn_del.setIcon(icon_del)
                btn_del.setIconSize(QSize(25, 25))
                btn_del.clicked.connect(partial(self.delete_agent, row_data))
                self.table_widget.setCellWidget(row_position, 5, btn_del)

                # Connect the double-click signal with the chat button click
                self.table_widget.itemDoubleClicked.connect(self.on_row_double_clicked)

        if self.table_widget.rowCount() > 0:
            # select agent-id
            if self.agent_id > 0:
                for row in range(self.table_widget.rowCount()):
                    if self.table_widget.item(row, 0).text() == str(self.agent_id):
                        self.table_widget.selectRow(row)
                        break
            else:
                self.table_widget.selectRow(0)

    def on_row_double_clicked(self, item):
        # Get the row of the item that was clicked
        row = item.row()

        # Simulate clicking the chat button in the same row
        btn_chat = self.table_widget.cellWidget(row, 4)
        btn_chat.click()

    def on_agent_selected(self):
        current_row = self.table_widget.currentRow()
        if current_row == -1: return
        sel_id = self.table_widget.item(current_row, 0).text()
        agent_config_json = sql.get_scalar('SELECT config FROM agents WHERE id = ?', (sel_id,))

        self.agent_id = int(self.table_widget.item(current_row, 0).text())
        self.agent_config = json.loads(agent_config_json) if agent_config_json else {}

        with block_signals(self.page_general, self.page_context, self.page_actions):  # , self.page_code):
            self.page_general.load()
            self.page_context.load()
            self.page_actions.load()
            self.page_voice.load()
            # self.page_code.load()

    def chat_with_agent(self, row_data):
        from agent.base import Agent
        id_value = row_data[0]  # self.table_widget.item(row_item, 0).text()
        self.main.page_chat.agent = Agent(agent_id=id_value)
        self.main.page_chat.load_bubbles()
        self.main.content.setCurrentWidget(self.main.page_chat)
        self.main.sidebar.btn_new_context.setChecked(True)

    def delete_agent(self, row_data):
        global PIN_STATE
        context_count = sql.get_results("""
            SELECT
                COUNT(*)
            FROM contexts
            WHERE agent_id = ?""", (row_data[0],))[0][0]

        has_contexts_msg = ''
        if context_count > 0:
            has_contexts_msg = 'This agent has contexts associated with it. Deleting this agent will delete all associated contexts. '

        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setText(f"{has_contexts_msg}Are you sure you want to delete this agent?")
        msg.setWindowTitle("Delete Agent")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

        current_pin_state = PIN_STATE
        PIN_STATE = True
        retval = msg.exec_()
        PIN_STATE = current_pin_state
        if retval != QMessageBox.Yes:
            return

        sql.execute("DELETE FROM contexts_messages WHERE context_id IN (SELECT id FROM contexts WHERE agent_id = ?);", (row_data[0],))
        sql.execute("DELETE FROM contexts WHERE agent_id = ?;", (row_data[0],))
        sql.execute("DELETE FROM agents WHERE id = ?;", (row_data[0],))
        self.load()

    def get_current_config(self):
        # ~CONF
        hh = 1
        # Retrieve the current values from the widgets and construct a new 'config' dictionary
        current_config = {
            'general.avatar_path': self.page_general.avatar_path,
            'general.use_plugin': self.page_general.plugin_combo.currentData(),
            'context.model': self.page_context.model_combo.currentData(),
            'context.sys_msg': self.page_context.sys_msg.toPlainText(),
            'context.auto_title': self.page_context.auto_title.isChecked(),
            'context.fallback_to_davinci': self.page_context.fallback_to_davinci.isChecked(),
            'context.max_messages': self.page_context.max_messages.value(),
            'actions.enable_actions': self.page_actions.enable_actions.isChecked(),
            'actions.source_directory': self.page_actions.source_directory.text(),
            'actions.replace_busy_action_on_new': self.page_actions.replace_busy_action_on_new.isChecked(),
            'actions.use_function_calling': self.page_actions.use_function_calling.isChecked(),
            'actions.use_validator': self.page_actions.use_validator.isChecked(),
            'actions.code_auto_run_seconds': self.page_actions.code_auto_run_seconds.text(),
            'voice.current_id': int(self.page_voice.current_id),
        }
        return json.dumps(current_config)

    def update_agent_config(self):
        current_config = self.get_current_config()
        sql.execute("UPDATE agents SET config = ? WHERE id = ?", (current_config, self.agent_id))
        self.main.page_chat.agent.load_agent()
        self.load()

    class Button_New_Agent(QPushButton):
        def __init__(self, parent):
            super().__init__(parent=parent, icon=QIcon())
            self.parent = parent
            self.clicked.connect(self.new_agent)
            self.icon = QIcon(QPixmap("./utils/resources/icon-new.png"))
            self.setIcon(self.icon)
            self.setFixedSize(25, 25)
            self.setIconSize(QSize(25, 25))

        def new_agent(self):
            global PIN_STATE
            current_pin_state = PIN_STATE
            PIN_STATE = True
            text, ok = QInputDialog.getText(self, 'New Agent', 'Enter a name for the agent:')

            # Check if the OK button was clicked
            if ok:
                # Display the entered value in a message box
                sql.execute("INSERT INTO `agents` (`name`, `config`) "
                                    "SELECT ? AS `name`,"
                                        "(SELECT value FROM settings WHERE field = 'global_config') AS config", (text,))
                self.parent.load()
            PIN_STATE = current_pin_state

    class Agent_Settings_SideBar(QWidget):
        def __init__(self, main, parent):
            super().__init__(parent=main)
            self.main = main
            self.parent = parent
            self.setObjectName("SettingsSideBarWidget")
            self.setAttribute(Qt.WA_StyledBackground, True)
            self.setProperty("class", "sidebar")

            font = QFont()
            font.setPointSize(13)  # Set font size to 20 points

            self.btn_general = self.Settings_SideBar_Button(main=main, text='General')
            self.btn_general.setFont(font)
            self.btn_general.setChecked(True)
            self.btn_context = self.Settings_SideBar_Button(main=main, text='Context')
            self.btn_context.setFont(font)
            self.btn_actions = self.Settings_SideBar_Button(main=main, text='Actions')
            self.btn_actions.setFont(font)
            self.btn_voice = self.Settings_SideBar_Button(main=main, text='Voice')
            self.btn_voice.setFont(font)

            self.layout = QVBoxLayout(self)
            self.layout.setSpacing(0)
            self.layout.setContentsMargins(0, 0, 0, 0)

            # Create a button group and add buttons to it
            self.button_group = QButtonGroup(self)
            self.button_group.addButton(self.btn_general, 0)
            self.button_group.addButton(self.btn_context, 1)
            self.button_group.addButton(self.btn_actions, 2)
            self.button_group.addButton(self.btn_voice, 3)  # 1

            # Connect button toggled signal
            self.button_group.buttonToggled[QAbstractButton, bool].connect(self.onButtonToggled)

            # self.layout.addStretch(1)

            self.layout.addWidget(self.btn_general)
            self.layout.addWidget(self.btn_context)
            self.layout.addWidget(self.btn_actions)
            self.layout.addWidget(self.btn_voice)
            self.layout.addStretch()

        def onButtonToggled(self, button, checked):
            if checked:
                index = self.button_group.id(button)
                self.parent.content.setCurrentIndex(index)
                self.parent.content.currentWidget().load()

        def updateButtonStates(self):
            # Check the appropriate button based on the current page
            stacked_widget = self.parent.content
            self.btn_context.setChecked(stacked_widget.currentWidget() == self.btn_context)
            self.btn_actions.setChecked(stacked_widget.currentWidget() == self.btn_actions)

        class Settings_SideBar_Button(QPushButton):
            def __init__(self, main, text=''):
                super().__init__(parent=main, icon=QIcon())
                self.main = main
                self.setProperty("class", "menuitem")
                # self.clicked.connect(self.goto_system_settings)
                self.setText(text)
                self.setFixedSize(75, 30)
                self.setCheckable(True)

    class Page_General_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent

            # Main layout for this widget
            main_layout = QVBoxLayout(self)
            main_layout.setAlignment(Qt.AlignCenter)  # Center the layout's content

            profile_layout = QHBoxLayout(self)
            profile_layout.setAlignment(Qt.AlignCenter)
            # Avatar - an image input field
            self.avatar_path = ''
            self.avatar = self.ClickableAvatarLabel(self)
            self.avatar.clicked.connect(self.change_avatar)

            # Name - a text field, so use QLineEdit
            self.name = QLineEdit()
            self.name.textChanged.connect(self.update_name)

            # Set the font size to 22 for the name field
            font = self.name.font()
            font.setPointSize(15)
            self.name.setFont(font)
            # centre the text
            self.name.setAlignment(Qt.AlignCenter)

            # Create a combo box for the plugin selection
            self.plugin_combo = PluginComboBox()
            self.plugin_combo.setFixedWidth(150)
            self.plugin_combo.setItemDelegate(AlignDelegate(self.plugin_combo))

            # self.plugin_combo.addItem("< No Plugin>", "")
            # self.plugin_combo.addItem("Open Interpreter", "openinterpreter")

            self.plugin_combo.currentIndexChanged.connect(self.plugin_changed)

            # Adding avatar and name to the main layout
            profile_layout.addWidget(self.avatar)  # Adding the avatar

            # add profile layout to main layout
            main_layout.addLayout(profile_layout)
            main_layout.addWidget(self.name)
            main_layout.addWidget(self.plugin_combo, alignment=Qt.AlignCenter)
            main_layout.addStretch()

        def load(self):  # , row):
            parent = self.parent

            with block_signals(self):
                self.avatar_path = (parent.agent_config.get('general.avatar_path', ''))
                try:
                    # self.page_general.avatar.setPixmap(QPixmap())
                    if parent.page_general.avatar_path == '':
                        raise Exception('No avatar path')
                    avatar_img = QPixmap(self.avatar_path)
                except Exception as e:
                    avatar_img = QPixmap("./utils/resources/icon-agent.png")
                self.avatar.setPixmap(avatar_img)
                self.avatar.update()
                current_row = parent.table_widget.currentRow()
                name_cell = parent.table_widget.item(current_row, 3)
                if name_cell:
                    self.name.setText(name_cell.text())
                active_plugin = parent.agent_config.get('general.use_plugin', '')
                # set plugin combo by key
                for i in range(self.plugin_combo.count()):
                    if self.plugin_combo.itemData(i) == active_plugin:
                        self.plugin_combo.setCurrentIndex(i)
                        break
                else:
                    self.plugin_combo.setCurrentIndex(0)

        def update_name(self):
            new_name = self.name.text()
            sql.execute("UPDATE agents SET name = ? WHERE id = ?", (new_name, self.parent.agent_id))
            self.parent.load()
            self.parent.main.page_chat.agent.load_agent()

        def plugin_changed(self):
            self.parent.update_agent_config()
            # set first item text to 'No Plugin' if no plugin is selected
            if self.plugin_combo.currentData() == '':
                self.plugin_combo.setItemText(0, "Choose Plugin")
            else:
                self.plugin_combo.setItemText(0, "< No Plugin >")

        class ClickableAvatarLabel(QLabel):
            # This creates a new signal called 'clicked' that the label will emit when it's clicked.
            clicked = Signal()

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.setAlignment(Qt.AlignCenter)
                self.setCursor(Qt.PointingHandCursor)  # Change mouse cursor to hand pointer for better UI indication
                self.setFixedSize(100, 100)
                self.setStyleSheet("border: 1px dashed rgb(200, 200, 200); border-radius: 50px;")  # A custom style for the empty label

            def mousePressEvent(self, event):
                super().mousePressEvent(event)
                if event.button() == Qt.LeftButton:  # Emit 'clicked' only for left button clicks
                    self.clicked.emit()

            def setPixmap(self, pixmap):
                # Override setPixmap to maintain the aspect ratio of the image
                super().setPixmap(pixmap.scaled(
                    self.width(), self.height(),
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation
                ))

            def paintEvent(self, event):
                # Override paintEvent to draw a circular image
                painter = QPainter(self)
                painter.setRenderHint(QPainter.Antialiasing)
                path = QPainterPath()
                path.addEllipse(0, 0, self.width(), self.height())
                painter.setClipPath(path)
                painter.drawPixmap(0, 0, self.pixmap())
                painter.end()

        def change_avatar(self):
            global PIN_STATE
            current_pin_state = PIN_STATE
            PIN_STATE = True
            options = QFileDialog.Options()
            fileName, _ = QFileDialog.getOpenFileName(self, "QFileDialog.getOpenFileName()", "",
                                                      "Images (*.png *.jpeg *.jpg *.bmp *.gif)", options=options)
            PIN_STATE = current_pin_state
            if fileName:
                self.avatar.setPixmap(QPixmap(fileName))
                self.avatar_path = fileName
                self.parent.update_agent_config()

    class Page_Context_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent

            self.form_layout = QFormLayout()

            self.model_combo = ModelComboBox()
            self.model_combo.setFixedWidth(150)
            # self.model_combo.setItemDelegate(AlignDelegate(self.model_combo))
            self.form_layout.addRow(QLabel('Model:'), self.model_combo)

            self.sys_msg = QTextEdit()
            self.sys_msg.setFixedHeight(150)  # Adjust height as per requirement
            self.form_layout.addRow(QLabel('System message:'), self.sys_msg)

            # Fallback to davinci - a checkbox
            self.fallback_to_davinci = QCheckBox()
            self.form_layout.addRow(QLabel('Fallback to davinci:'), self.fallback_to_davinci)

            # max-messages - a numeric input, so use QSpinBox
            self.max_messages = QSpinBox()
            self.max_messages.setFixedWidth(150)  # Consistent width
            self.form_layout.addRow(QLabel('Max messages:'), self.max_messages)

            # Fallback to davinci - a checkbox
            self.auto_title = QCheckBox()
            self.form_layout.addRow(QLabel('Auto title:'), self.auto_title)

            # Add the form layout to a QVBoxLayout and add a spacer to push everything to the top
            self.main_layout = QVBoxLayout(self)
            self.main_layout.addLayout(self.form_layout)
            spacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
            self.main_layout.addItem(spacer)

            self.model_combo.currentIndexChanged.connect(parent.update_agent_config)
            self.sys_msg.textChanged.connect(parent.update_agent_config)
            self.fallback_to_davinci.stateChanged.connect(parent.update_agent_config)
            self.max_messages.valueChanged.connect(parent.update_agent_config)
            self.auto_title.stateChanged.connect(parent.update_agent_config)

        def load(self):
            parent = self.parent
            with block_signals(self):
                current_data = parent.agent_config.get('context.model', '')
                self.model_combo.setCurrentIndex(self.model_combo.findData(current_data))
                self.sys_msg.setText(parent.agent_config.get('context.sys_msg', ''))
                self.sys_msg.moveCursor(QTextCursor.End)
                self.auto_title.setChecked(parent.agent_config.get('context.auto_title', True))
                self.fallback_to_davinci.setChecked(parent.agent_config.get('context.fallback_to_davinci', False))
                self.max_messages.setValue(parent.agent_config.get('context.max_messages', 5))

    class Page_Actions_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent

            self.form_layout = QFormLayout()

            # Enable actions - checkbox
            self.enable_actions = QCheckBox()
            self.form_layout.addRow(QLabel('Enable actions:'), self.enable_actions)

            # Source directory - path field and button to trigger folder dialog
            self.source_directory = QLineEdit()
            self.browse_button = QPushButton("..")
            self.browse_button.setFixedSize(25, 25)
            self.browse_button.clicked.connect(self.browse_for_folder)

            # Create labels as member variables
            self.label_source_directory = QLabel('Source Directory:')
            self.label_replace_busy_action_on_new = QLabel('Replace busy action on new:')
            self.label_use_function_calling = QLabel('Use function calling:')
            self.label_use_validator = QLabel('Use validator:')
            self.label_code_auto_run_seconds = QLabel('Code auto-run seconds:')

            hbox = QHBoxLayout()
            hbox.addWidget(self.browse_button)
            hbox.addWidget(self.source_directory)
            self.form_layout.addRow(self.label_source_directory, hbox)

            self.replace_busy_action_on_new = QCheckBox()
            self.form_layout.addRow(self.label_replace_busy_action_on_new, self.replace_busy_action_on_new)

            self.use_function_calling = QCheckBox()
            self.form_layout.addRow(self.label_use_function_calling, self.use_function_calling)

            self.use_validator = QCheckBox()
            self.form_layout.addRow(self.label_use_validator, self.use_validator)

            self.code_auto_run_seconds = QLineEdit()
            self.code_auto_run_seconds.setValidator(QIntValidator(0, 300))
            self.form_layout.addRow(self.label_code_auto_run_seconds, self.code_auto_run_seconds)

            self.setLayout(self.form_layout)

            # Set initial state
            self.toggle_enabled_state()

            self.enable_actions.stateChanged.connect(self.toggle_enabled_state)
            self.enable_actions.stateChanged.connect(parent.update_agent_config)
            self.source_directory.textChanged.connect(parent.update_agent_config)
            self.replace_busy_action_on_new.stateChanged.connect(parent.update_agent_config)
            self.use_function_calling.stateChanged.connect(parent.update_agent_config)
            self.use_validator.stateChanged.connect(parent.update_agent_config)
            self.code_auto_run_seconds.textChanged.connect(parent.update_agent_config)

        def load(self):
            parent = self.parent
            with block_signals(self):
                self.enable_actions.setChecked(parent.agent_config.get('actions.enable_actions', False))
                self.source_directory.setText(parent.agent_config.get('actions.source_directory', ''))
                self.replace_busy_action_on_new.setChecked(parent.agent_config.get('actions.replace_busy_action_on_new', False))
                self.use_function_calling.setChecked(parent.agent_config.get('actions.use_function_calling', False))
                self.use_validator.setChecked(parent.agent_config.get('actions.use_validator', False))
                self.code_auto_run_seconds.setText(str(parent.agent_config.get('actions.code_auto_run_seconds', 5)))

        def browse_for_folder(self):
            folder = QFileDialog.getExistingDirectory(self, "Select Source Directory")
            if folder:
                self.source_directory.setText(folder)

        def toggle_enabled_state(self):
            global TEXT_COLOR
            is_enabled = self.enable_actions.isChecked()

            # Set enabled/disabled state for the widgets
            self.source_directory.setEnabled(is_enabled)
            self.browse_button.setEnabled(is_enabled)
            self.replace_busy_action_on_new.setEnabled(is_enabled)
            self.use_function_calling.setEnabled(is_enabled)
            self.use_validator.setEnabled(is_enabled)

            # Update label colors based on enabled state
            if is_enabled:
                color = TEXT_COLOR  # or any other color when enabled
            else:
                color = "#4d4d4d"  # or any other color when disabled

            self.label_source_directory.setStyleSheet(f"color: {color}")
            self.label_replace_busy_action_on_new.setStyleSheet(f"color: {color}")
            self.label_use_function_calling.setStyleSheet(f"color: {color}")
            self.label_use_validator.setStyleSheet(f"color: {color}")

    # class Page_Plugins_Settings(QWidget):
    #     def __init__(self, parent):
    #         super().__init__(parent=parent)
    #         self.parent = parent
    #         self.form_layout = QFormLayout()
    #
    #         # Enable code interpreter - checkbox
    #         self.enable_code_interpreter = QCheckBox()
    #         self.form_layout.addRow(QLabel('Use plugin:'), self.enable_code_interpreter)
    #
    #         # Use GPT4 - checkbox
    #         self.use_gpt4 = QCheckBox()
    #         self.form_layout.addRow(QLabel('Use GPT4:'), self.use_gpt4)
    #
    #         # Create labels as member variables
    #         self.label_enable_code_interpreter = QLabel('Enable code interpreter:')
    #         self.label_auto_run_seconds = QLabel('Auto run seconds:')
    #         self.label_use_gpt4 = QLabel('Use GPT4:')
    #
    #         # Set the layout
    #         self.setLayout(self.form_layout)
    #
    #         # Connect the signals to the slots
    #         self.enable_code_interpreter.stateChanged.connect(parent.update_agent_config)
    #         self.use_gpt4.stateChanged.connect(parent.update_agent_config)
    #
    #     def load(self):
    #         parent = self.parent
    #         with block_signals(self):
    #             self.enable_code_interpreter.setChecked(parent.agent_config.get('code.enable_code_interpreter', False))
    #             self.use_gpt4.setChecked(parent.agent_config.get('code.use_gpt4', False))


    class Page_Voice_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            # UI setup
            self.layout = QVBoxLayout(self)

            # Search panel setup
            self.search_panel = QWidget(self)
            self.search_layout = QHBoxLayout(self.search_panel)
            self.api_dropdown = APIComboBox(self, first_item='ALL')
            # self.api_dropdown.addItem("ALL", 0)  # adding "ALL" option with id=0
            self.search_field = QLineEdit(self)
            self.search_layout.addWidget(QLabel("API:"))
            self.search_layout.addWidget(self.api_dropdown)
            self.search_layout.addWidget(QLabel("Search:"))
            self.search_layout.addWidget(self.search_field)
            self.layout.addWidget(self.search_panel)

            self.table = BaseTableWidget(self)
            # self.table.setSelectionMode(QTableWidget.SingleSelection)
            # self.table.setSelectionBehavior(QTableWidget.SelectRows)
            # palette = self.table.palette()
            # palette.setColor(QPalette.Highlight, QColor(SECONDARY_COLOR))
            # palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
            # palette.setColor(QPalette.Text, QColor(TEXT_COLOR))
            # self.table.setPalette(palette)

            # Creating a new QWidget to hold the buttons
            self.buttons_panel = QWidget(self)
            self.buttons_layout = QHBoxLayout(self.buttons_panel)
            self.buttons_layout.setAlignment(Qt.AlignRight)  # Aligning buttons to the right

            # Set as voice button
            self.set_voice_button = QPushButton("Set as voice", self)
            self.set_voice_button.setFixedWidth(150)  # Set the width to a normal button width
            # Test voice button
            self.test_voice_button = QPushButton("Test voice", self)
            self.test_voice_button.setFixedWidth(150)  # Set the width to a normal button width
            # Adding buttons to the layout
            self.buttons_layout.addWidget(self.set_voice_button)
            self.buttons_layout.addWidget(self.test_voice_button)
            self.layout.addWidget(self.table)
            self.layout.addWidget(self.buttons_panel)  # Adding the buttons panel to the main layout
            # Connect button click and other UI events
            self.set_voice_button.clicked.connect(self.set_as_voice)
            self.test_voice_button.clicked.connect(self.test_voice)  # You will need to define the 'test_voice' method

            self.api_dropdown.currentIndexChanged.connect(self.filter_table)
            self.search_field.textChanged.connect(self.filter_table)

            # self.table.verticalHeader().hide()
            # self.table.hideColumn(0)  # Hide ID column

            self.current_id = 0

        def load(self):
            # Database fetch and display
            with block_signals(self):
                self.load_data_from_db()
                # self.load_apis()
                self.current_id = self.parent.agent_config.get('voice.current_id', 0)
                self.highlight_and_select_current_voice()

        def load_data_from_db(self):
            # Fetch all voices initially
            self.all_voices, self.col_names = sql.get_results("""
                SELECT
                    v.`id`,
                    a.`name` AS api_id,
                    v.`display_name`,
                    v.`known_from`,
                    v.`uuid`,
                    v.`added_on`,
                    v.`updated_on`,
                    v.`rating`,
                    v.`creator`,
                    v.`lang`,
                    v.`deleted`,
                    v.`fav`,
                    v.`full_in_prompt`,
                    v.`verb`,
                    v.`add_prompt`
                FROM `voices` v
                LEFT JOIN apis a
                    ON v.api_id = a.id""", incl_column_names=True)

            self.display_data_in_table(self.all_voices)

        # def load_apis(self):
        #     self.api_dropdown
        #     # Assuming that the first item in the tuple is 'ID' and the second is 'name'
        #     apis = sql.get_results("SELECT ID, name FROM apis")
        #     for api in apis:
        #         # Use integer indices instead of string keys
        #         api_id = api[0]  # 'ID' is at index 0
        #         api_name = api[1]  # 'name' is at index 1
        #         self.api_dropdown.addItem(api_name, api_id)

        def highlight_and_select_current_voice(self):
            """Highlights the current voice in the table and selects its row."""
            # current_voice_id = self.parent.agent_config.get('voice.current_id', None)
            if not self.current_id or self.current_id == 0:
                return

            for row_index in range(self.table.rowCount()):
                if self.table.item(row_index, 0).text() == str(self.current_id):
                    # Make the text bold
                    for col_index in range(self.table.columnCount()):
                        item = self.table.item(row_index, col_index)
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)

                    # Select this row
                    self.table.selectRow(row_index)
                    break

        def filter_table(self):
            # api_id = self.api_dropdown.currentData()
            api_name = self.api_dropdown.currentText()
            search_text = self.search_field.text().lower()

            filtered_voices = []
            for voice in self.all_voices:
                # Check if voice matches the selected API and contains the search text in 'name' or 'known_from'
                # (using the correct indices for your data)
                if (api_name == 'ALL' or str(voice[1]) == api_name) and \
                        (search_text in voice[2].lower() or search_text in voice[3].lower()):
                    filtered_voices.append(voice)

            self.display_data_in_table(filtered_voices)

        def display_data_in_table(self, voices):
            self.table.setRowCount(len(voices))
            # Add an extra column for the play buttons
            self.table.setColumnCount(len(voices[0]) if voices else 0)
            # Add a header for the new play button column
            self.table.setHorizontalHeaderLabels(self.col_names)
            self.table.hideColumn(0)

            for row_index, row_data in enumerate(voices):
                for col_index, cell_data in enumerate(row_data):  # row_data is a tuple, not a dict
                    self.table.setItem(row_index, col_index, QTableWidgetItem(str(cell_data)))

        def set_as_voice(self):
            current_row = self.table.currentRow()
            if current_row == -1:
                QMessageBox.warning(self, "Selection Error", "Please select a voice from the table!")
                return

            self.current_id = self.table.item(current_row, 0).text()
            self.parent.update_agent_config()  # 'voice.current_id', voice_id)
            self.parent.main.page_chat.agent.load_agent()
            self.load()
            # self.parent.update_agent_config()
            # Further actions can be taken using voice_id or the data of the selected row
            # QMessageBox.information(self, "Voice Set", f"Voice with ID {self.current_id} has been set!")

        def test_voice(self):
            # Implement the functionality to test the voice
            pass

class Page_Contexts(ContentPage):
    def __init__(self, main):
        super().__init__(main=main, title='Contexts')
        self.main = main

        self.table_widget = QTableWidget(0, 5, self)

        # self.load_contexts()

        self.table_widget.setColumnWidth(3, 45)
        self.table_widget.setColumnWidth(4, 45)
        # self.table_widget.setColumnWidth(1, 450)
        self.table_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        # self.table_widget.setSelectionMode(QTableWidget.Sin)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.hideColumn(0)
        self.table_widget.horizontalHeader().hide()
        self.table_widget.verticalHeader().hide()
        self.table_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)

        palette = self.table_widget.palette()
        palette.setColor(QPalette.Highlight, QColor(SECONDARY_COLOR))  # Setting it to red
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))  # Setting text color to white
        palette.setColor(QPalette.Text, QColor(TEXT_COLOR))  # Setting unselected text color to purple
        self.table_widget.setPalette(palette)
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        # Add the table to the layout
        self.layout.addWidget(self.table_widget)

    def load(self):  # Load Contexts
        self.table_widget.setRowCount(0)
        data = sql.get_results("""
            SELECT
                c.id,
                c.summary,
                a.name,
                '' AS goto_button,
                '' AS del_button
            FROM contexts c
            LEFT JOIN agents a
                ON c.agent_id = a.id
            LEFT JOIN (
                SELECT
                    context_id,
                    MAX(id) as latest_message_id
                FROM contexts_messages
                GROUP BY context_id
            ) cm ON c.id = cm.context_id
            WHERE c.parent_id IS NULL
            ORDER BY
                CASE WHEN cm.latest_message_id IS NULL THEN 0 ELSE 1 END,
                COALESCE(cm.latest_message_id, 0) DESC, 
                c.id DESC
            """)
        # first_desc = 'CURRENT CONTEXT'

        icon_chat = QIcon('./utils/resources/icon-chat.png')
        icon_del = QIcon('./utils/resources/icon-delete.png')

        for row_data in data:
            # if first_desc:
            #     row_data = [row_data[0], first_desc, row_data[2], row_data[3]]
            #     first_desc = None
            row_position = self.table_widget.rowCount()
            self.table_widget.insertRow(row_position)
            for column, item in enumerate(row_data):
                self.table_widget.setItem(row_position, column, QTableWidgetItem(str(item)))

            if row_data[2] is None:  # If agent_name is NULL
                self.table_widget.setSpan(row_position, 1, 1, 2)  # Make the summary cell span over the next column

            # set btn icon
            btn_chat = QPushButton('')
            btn_chat.setIcon(icon_chat)
            btn_chat.setIconSize(QSize(25, 25))
            btn_chat.clicked.connect(partial(self.goto_context, row_data))
            self.table_widget.setCellWidget(row_position, 3, btn_chat)

            # set btn icon
            btn_delete = QPushButton('')
            btn_delete.setIcon(icon_del)
            btn_delete.setIconSize(QSize(25, 25))
            btn_delete.clicked.connect(partial(self.delete_context, row_data))
            self.table_widget.setCellWidget(row_position, 4, btn_delete)

            # Connect the double-click signal with the chat button click
            self.table_widget.itemDoubleClicked.connect(self.on_row_double_clicked)

    def on_row_double_clicked(self, item):
        # Get the row of the item that was clicked
        row = item.row()

        # Simulate clicking the chat button in the same row
        btn_chat = self.table_widget.cellWidget(row, 3)  # Assuming the chat button is in column 3
        btn_chat.click()

    def goto_context(self, row_item):
        from agent.base import Agent
        id_value = row_item[0]  # self.table_widget.item(row_item, 0).text()
        self.main.page_chat.agent = Agent(agent_id=None, context_id=id_value)
        self.main.page_chat.load_bubbles()
        self.main.content.setCurrentWidget(self.main.page_chat)
        self.main.sidebar.btn_new_context.setChecked(True)
        # print(f"goto ID: {id_value}")

    def delete_context(self, row_item):
        from agent.base import Agent
        global PIN_STATE
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setText("Are you sure you want to permanently delete this context?")
        msg.setWindowTitle("Delete Context")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

        current_pin_state = PIN_STATE
        PIN_STATE = True
        retval = msg.exec_()
        PIN_STATE = current_pin_state
        if retval != QMessageBox.Yes:
            return

        context_id = row_item[0]
        sql.execute("DELETE FROM contexts_messages WHERE context_id = ?;", (context_id,))
        sql.execute("DELETE FROM contexts WHERE id = ?;", (context_id,))
        self.load()

        if self.main.page_chat.agent.context.message_history.context_id == context_id:
            self.main.page_chat.agent = Agent(agent_id=None)


class Page_Chat(QScrollArea):
    def __init__(self, main):
        super().__init__(parent=main)
        from agent.base import Agent
        self.agent = Agent(agent_id=None)
        self.main = main
        # self.setFocusPolicy(Qt.StrongFocus)

        self.chat_bubbles = []
        self.last_assistant_bubble = None

        # Overall layout for the page
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # TopBar pp
        self.topbar = self.Top_Bar(self)
        self.layout.addWidget(self.topbar)

        # Scroll area for the chat
        self.scroll_area = QScrollArea(self)  # CustomScrollArea(self)  #
        self.chat = QWidget(self.scroll_area)
        self.chat_scroll_layout = QVBoxLayout(self.chat)
        self.chat_scroll_layout.addStretch(1)

        self.scroll_area.setWidget(self.chat)
        self.scroll_area.setWidgetResizable(True)

        self.layout.addWidget(self.scroll_area)

        # self.installEventFilterRecursively(self.scroll_area.viewport())
        self.installEventFilterRecursively(self)
        # for child in self.children():
        #     if isinstance(child, QWidget):
        #         self.installEventFilterRecursively(child)
        # self.scroll_area.viewport().installEventFilter(self)

        self.temp_text_size = None

    # def wheelEvent(self, event):
    #     if event.modifiers() & Qt.ControlModifier:
    #         delta = event.angleDelta().y()
    #         if delta > 0:
    #             self.temp_zoom_in()
    #         else:
    #             self.temp_zoom_out()
    #         # event.accept()  # Stop further propagation of the wheel event
    #     else:
    #         super().wheelEvent(event)

    # def keyReleaseEvent(self, event):
    #     if event.key() == Qt.Key_Control:
    #         self.update_text_size()
    #         event.accept()  # In this case, we'll stop further propagation of the key release event as well
    #     else:
    #         super().keyReleaseEvent(event)

    def load(self):
        self.load_bubbles()
        QTimer.singleShot(1, self.scroll_to_end)


    def eventFilter(self, watched, event):
        # If the event is a wheel event and the Ctrl key is pressed
        if event.type() == QEvent.Wheel and event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()

            # Zoom in or out based on the wheel direction
            if delta > 0:
                self.temp_zoom_in()
            else:
                self.temp_zoom_out()

            # After zoom operation, explicitly refocus on the current widget
            # This ensures that subsequent wheel events are still caught by this widget
            # QApplication.instance().processEvents()  # Process any pending events
            # self.setFocus()  # Explicitly request focus

            return True  # Stop further propagation of the wheel event

        # If the event is a KeyRelease event and it's the Ctrl key
    # If the event is a KeyRelease event and it's the Ctrl key
        elif event.type() == QEvent.KeyRelease:
            if event.key() == Qt.Key_Control:
                self.update_text_size()

                # Explicitly refocus after the Ctrl key is released
                # QApplication.instance().processEvents()  # Process any pending events
                # self.chat.setFocus()  # Explicitly request focus

                return True  # In this case, we'll stop further propagation of the key release event as well


        return super().eventFilter(watched, event)

    # def eventFilter(self, watched, event):
    #     # If the event is a wheel event
    #     if event.type() == QEvent.Wheel:
    #         if event.modifiers() & Qt.ControlModifier:
    #             delta = event.angleDelta().y()
    #
    #             if delta > 0:
    #                 self.temp_zoom_in()
    #             else:
    #                 self.temp_zoom_out()
    #
    #             # self.setFocus(Qt.MouseFocusReason)  # Refocus after zoom operation
    #             return True  # Stop further propagation of the event
    #
    #     # Check for key release events
    #     if event.type() == QEvent.KeyRelease:
    #         if event.key() == Qt.Key_Control:
    #             # If Ctrl is released, update the configuration with the last temporary text size
    #             self.update_text_size()
    #
    #     return super().eventFilter(watched, event)

    # def keyReleaseEvent(self, event):
    #     if self.temp_text_size is None:
    #         return
    #     if event.key() == Qt.Key_Control:
    #         self.update_text_size()
    #         self.setFocus()

    def temp_zoom_in(self):
        if not self.temp_text_size:
            self.temp_text_size = config.get_value('display.text_size')
        if self.temp_text_size >= 50:
            return
        self.temp_text_size += 1
        # self.main.page_settings.update_config('display.text_size', self.temp_text_size)
        self.load_bubbles()
        # self.setFocus()

    def temp_zoom_out(self):
        if not self.temp_text_size:
            self.temp_text_size = config.get_value('display.text_size')
        if self.temp_text_size <= 7:
            return
        self.temp_text_size -= 1
        # self.main.page_settings.update_config('display.text_size', self.temp_text_size)
        self.load_bubbles()
        # self.setFocus()

    def update_text_size(self):
        # Call this method to update the configuration once Ctrl is released
        if self.temp_text_size is None:
            return
        self.main.page_settings.update_config('display.text_size', self.temp_text_size)
        self.temp_text_size = None

    def installEventFilterRecursively(self, widget):
        widget.installEventFilter(self)
        for child in widget.children():
            if isinstance(child, QWidget):
                self.installEventFilterRecursively(child)

    class Top_Bar(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.setMouseTracking(True)
            self.setFixedHeight(40)
            self.topbar_layout = QHBoxLayout(self)
            self.topbar_layout.setSpacing(0)
            # self.topbar_layout.setContentsMargins(0, 0, 0, 0)
            self.topbar_layout.setContentsMargins(5, 5, 5, 10)

            agent_name = self.parent().agent.name
            agent_avatar_path = self.parent().agent.config.get('general.avatar_path', '')
            try:
                # self.page_general.avatar.setPixmap(QPixmap())
                if agent_avatar_path == '':
                    raise Exception('No avatar path')
                avatar_img = QPixmap(agent_avatar_path)
            except Exception as e:
                avatar_img = QPixmap("./utils/resources/icon-agent.png")
            # Step 1: Load the image
            # pixmap = QPixmap("path_to_your_image_here")  # put the correct path of your image

            circular_pixmap = create_circular_pixmap(avatar_img)

            # Step 3: Set the pixmap on a QLabel
            self.profile_pic_label = QLabel(self)
            self.profile_pic_label.setPixmap(circular_pixmap)
            self.profile_pic_label.setFixedSize(50, 30)  # set the QLabel size to the same as the pixmap
            # self.profile_pic_label.setStyleSheet(
            #     "border: 1px solid rgb(200, 200, 200); border-radius: 15px;")  # A custom style for the empty label

            # Step 4: Add QLabel to your layout
            self.topbar_layout.addWidget(self.profile_pic_label)

            self.agent_name_label = QLabel(self)
            self.agent_name_label.setText(agent_name)
            font = self.agent_name_label.font()
            font.setPointSize(15)
            self.agent_name_label.setFont(font)
            self.agent_name_label.setStyleSheet("QLabel:hover { color: #dddddd; }")
            self.agent_name_label.mousePressEvent = self.agent_name_clicked
            self.agent_name_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.topbar_layout.addWidget(self.agent_name_label)

            self.topbar_layout.addStretch()

            self.button_container = QWidget(self)
            button_layout = QHBoxLayout(self.button_container)  # Layout for the container
            button_layout.setSpacing(5)  # Set spacing between buttons, adjust to your need
            button_layout.setContentsMargins(0, 0, 20, 0)  # Optional: if you want to reduce space from the container's margins

            # Create buttons
            self.btn_prev_context = QPushButton(icon=QIcon('./utils/resources/icon-left-arrow.png'))
            self.btn_next_context = QPushButton(icon=QIcon('./utils/resources/icon-right-arrow.png'))
            self.btn_prev_context.setFixedSize(25, 25)
            self.btn_next_context.setFixedSize(25, 25)
            self.btn_prev_context.clicked.connect(self.previous_context)
            self.btn_next_context.clicked.connect(self.next_context)
            # ... add as many buttons as you need

            # Add buttons to the container layout instead of the button group
            button_layout.addWidget(self.btn_prev_context)
            button_layout.addWidget(self.btn_next_context)
            # ... add buttons to the layout

            # Add the container to the top bar layout
            self.topbar_layout.addWidget(self.button_container)

            self.button_container.hide()

        def previous_context(self):
            context_id = self.parent().agent.context.message_history.context_id
            prev_context_id = sql.get_scalar("SELECT id FROM contexts WHERE id < ? AND parent_id IS NULL ORDER BY id DESC LIMIT 1;", (context_id,))
            if prev_context_id:
                self.parent().goto_context(prev_context_id)
                self.btn_next_context.setEnabled(True)
            else:
                self.btn_prev_context.setEnabled(False)

        def next_context(self):
            context_id = self.parent().agent.context.message_history.context_id
            next_context_id = sql.get_scalar("SELECT id FROM contexts WHERE id > ? AND parent_id IS NULL ORDER BY id LIMIT 1;", (context_id,))
            if next_context_id:
                self.parent().goto_context(next_context_id)
                self.btn_prev_context.setEnabled(True)
            else:
                self.btn_next_context.setEnabled(False)

        def enterEvent(self, event):
            self.showButtonGroup()

        def leaveEvent(self, event):
            self.hideButtonGroup()

        def showButtonGroup(self):
            self.button_container.show()

        def hideButtonGroup(self):
            self.button_container.hide()

        def agent_name_clicked(self, event):
            self.parent().main.content.setCurrentWidget(self.parent().main.page_agents)

        def set_agent(self, agent):
            agent_name = agent.name
            agent_avatar_path = agent.config.get('general.avatar_path', '')
            self.agent_name_label.setText(agent_name)
            # Update the profile picture
            try:
                if agent_avatar_path == '':
                    raise Exception('No avatar path')
                avatar_img = QPixmap(agent_avatar_path)
            except Exception as e:
                avatar_img = QPixmap("./utils/resources/icon-agent.png")

            # Create a circular profile picture
            circular_pixmap = create_circular_pixmap(avatar_img)

            # Update the QLabel with the new pixmap
            self.profile_pic_label.setPixmap(circular_pixmap)

    #
    class MessageBubbleBase(QTextEdit):
        def __init__(self, msg_id, text, viewport, role, parent):
            super().__init__(parent=parent)
            if role not in ('user', 'code'):
                self.setReadOnly(True)
            self.installEventFilter(self)

            self.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding,
                QtWidgets.QSizePolicy.Expanding
            )
            self.parent = parent
            self.msg_id = msg_id
            self.agent = parent.agent
            self.role = role
            self.setProperty("class", "bubble")
            self.setProperty("class", role)
            self._viewport = viewport
            self.margin = QMargins(6, 0, 6, 0)
            self.text = ''
            self.original_text = text

            text_font = config.get_value('display.text_font')
            size_font = self.parent.temp_text_size if self.parent.temp_text_size else config.get_value('display.text_size')
            self.font = QFont()  # text_font, size_font)
            if text_font != '': self.font.setFamily(text_font)
            self.font.setPointSize(size_font)
            self.setCurrentFont(self.font)

            self.append_text(text)

        def calculate_button_position(self):
            button_width = 32
            button_height = 32
            button_x = self.width() - button_width
            button_y = self.height() - button_height
            return QRect(button_x, button_y, button_width, button_height)

        def append_text(self, text):
            self.text += text
            self.original_text = self.text
            self.setPlainText(self.text)
            self.update_size()

        def update_size(self):
            # self.text = self.toPlainText()
            self.setFixedSize(self.sizeHint())
            if hasattr(self, 'btn_resend'):
                self.btn_resend.setGeometry(self.calculate_button_position())
            self.updateGeometry()
            self.parent.updateGeometry()

        def sizeHint(self):
            lr = self.margin.left() + self.margin.right()
            tb = self.margin.top() + self.margin.bottom()

            doc = self.document().clone()
            doc.setDefaultFont(self.font)
            doc.setPlainText(self.text)
            doc.setTextWidth((self._viewport.width() - lr) * 0.8)

            return QSize(int(doc.idealWidth() + lr), int(doc.size().height() + tb))

        def minimumSizeHint(self):
            return self.sizeHint()

        def keyPressEvent(self, event):
            super().keyPressEvent(event)

    class MessageBubbleUser(MessageBubbleBase):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            self.btn_resend = self.BubbleButton_Resend(self)
            self.btn_resend.setGeometry(self.calculate_button_position())
            self.btn_resend.hide()

            self.textChanged.connect(self.text_editted)

        def text_editted(self):
            self.text = self.toPlainText()
            self.update_size()

        def check_and_toggle_resend_button(self):
            if self.toPlainText() != self.original_text:
                self.btn_resend.show()
            else:
                self.btn_resend.hide()

        def keyPressEvent(self, event):
            super().keyPressEvent(event)
            self.check_and_toggle_resend_button()
            # self.update_size()

        class BubbleButton_Resend(QPushButton):
            def __init__(self, parent=None):
                super().__init__(parent=parent, icon=QIcon())
                self.setProperty("class", "resend")
                self.clicked.connect(self.resend_msg)

                icon = QIcon(QPixmap("./utils/resources/icon-send.png"))
                self.setIcon(icon)

            def resend_msg(self):
                # display popup msg saying coming soon
                popup = QMessageBox()
                popup.setWindowTitle("Coming Soon")
                popup.setText("This feature is coming soon!")
                popup.setIcon(QMessageBox.Information)
                popup.setStandardButtons(QMessageBox.Ok)
                popup.exec_()

    class MessageBubbleCode(MessageBubbleBase):
        def __init__(self, msg_id, text, viewport, role, parent, start_timer=False):
            super().__init__(msg_id, text, viewport, role, parent)

            lang, code = self.split_lang_and_code(text)
            self.append_text(code)
            self.setToolTip(f'{lang} code')
            self.tag = lang
            self.btn_rerun = self.BubbleButton_Rerun_Code(self)
            self.btn_rerun.setGeometry(self.calculate_button_position())
            self.btn_rerun.hide()

            if start_timer:
                self.countdown_stopped = False
                self.countdown = int(self.agent.config.get('actions.code_auto_run_seconds', 5))  #
                self.countdown_button = self.CountdownButton(self)
                self.countdown_button.move(self.btn_rerun.x() - 20, self.btn_rerun.y() + 4)  # Adjust the position as needed

                self.countdown_button.clicked.connect(self.countdown_stop_btn_clicked)

                self.timer = QTimer(self)
                self.timer.timeout.connect(self.update_countdown)
                self.timer.start(1000)  # Start countdown timer with 1-second interval

        def countdown_stop_btn_clicked(self):
            self.countdown_stopped = True
            self.countdown_button.hide()

        def split_lang_and_code(self, text):
            if text.startswith('```') and text.endswith('```'):
                lang, code = text[3:-3].split('\n', 1)
                # code = code.rstrip('\n')
                return lang, code
            return None, text

        def enterEvent(self, event):
            self.check_and_toggle_rerun_button()
            self.reset_countdown()
            super().enterEvent(event)

        def leaveEvent(self, event):
            self.check_and_toggle_rerun_button()
            self.reset_countdown()
            super().leaveEvent(event)

        def update_countdown(self):
            if self.countdown > 0:
                # if True:  # not self.main.parent().parent().parent().expanded:
                #     self.reset_countdown()
                self.countdown -= 1
                self.countdown_button.setText(f"{self.countdown}")
            else:
                self.timer.stop()
                self.countdown_button.hide()
                if hasattr(self, 'countdown_stopped'):
                    self.countdown_stopped = True

                self.btn_rerun.click()

        def reset_countdown(self):
            countdown_stopped = getattr(self, 'countdown_stopped', True)
            if countdown_stopped: return
            self.timer.stop()
            self.countdown = int(self.agent.config.get('actions.code_auto_run_seconds', 5))  # 5  # Reset countdown to 5 seconds
            self.countdown_button.setText(f"{self.countdown}")
            # if self.main.parent().parent().expanded and not self.underMouse():
            if not self.underMouse():
                self.timer.start()  # Restart the timer

        def check_and_toggle_rerun_button(self):
            if self.underMouse():
                self.btn_rerun.show()
            else:
                self.btn_rerun.hide()

        class BubbleButton_Rerun_Code(QPushButton):
            def __init__(self, parent=None):
                super().__init__(parent=parent, icon=QIcon())
                self.bubble = parent
                self.setProperty("class", "rerun")
                self.clicked.connect(self.rerun_code)

                icon = QIcon(QPixmap("./utils/resources/icon-run.png"))
                self.setIcon(icon)

            def rerun_code(self):
                # Implement the functionality for rerunning the code
                pass

        class CountdownButton(QPushButton):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.setText(str(parent.agent.config.get('actions.code_auto_run_seconds', 5)))  # )
                self.setIcon(QIcon())  # Initially, set an empty icon
                self.setStyleSheet("color: white; background-color: transparent;")
                self.setFixedHeight(22)
                self.setFixedWidth(22)

            def enterEvent(self, event):
                icon = QIcon(QPixmap("./utils/resources/close.png"))
                self.setIcon(icon)
                self.setText("")  # Clear the text when displaying the icon
                super().enterEvent(event)

            def leaveEvent(self, event):
                self.setIcon(QIcon())  # Clear the icon
                self.setText(str(self.parent().countdown))  # Reset the text to the current countdown value
                super().leaveEvent(event)

        def contextMenuEvent(self, event):
            global PIN_STATE
            # Create the standard context menu
            menu = self.createStandardContextMenu()

            # Add a separator to distinguish between standard and custom actions
            menu.addSeparator()

            # Create your custom actions
            action_one = menu.addAction("Action One")
            action_two = menu.addAction("Action Two")

            # Connect actions to functions
            action_one.triggered.connect(self.action_one_function)
            action_two.triggered.connect(self.action_two_function)

            # Highlight the bubble visually
            # self.highlight_bubble()

            current_pin_state = PIN_STATE
            PIN_STATE = True
            # Show the context menu at current mouse position
            menu.exec_(event.globalPos())
            PIN_STATE = current_pin_state

            # Revert the highlight after the menu is closed
            # self.unhighlight_bubble()

        def action_one_function(self):
            # Do something for action one
            pass

        def action_two_function(self):
            # Do something for action two
            pass

    def load_new_code_bubbles(self):
        last_bubble_id = 0
        for bubble in reversed(self.chat_bubbles):
            if bubble.msg_id == -1: continue
            last_bubble_id = bubble.msg_id  # todo - dirty
            break

        # last_bubble_id = self.chat_bubbles[-1].msg_id
        msgs = self.agent.context.message_history.get(msg_limit=30,
                                                      pad_consecutive=False,
                                                      only_role_content=False,
                                                      incl_roles=('code',),
                                                      from_msg_id=last_bubble_id + 1)
        for msg in msgs:
            self.insert_bubble(msg)

    def load_bubbles(self):  # , is_first_load=False):  # todo - rename
        self.clear_bubbles()
        msgs = self.agent.context.message_history.get(msg_limit=30,
                                                      pad_consecutive=False,
                                                      only_role_content=False,
                                                      incl_roles=('user', 'assistant', 'code'))
        for msg in msgs:
            self.insert_bubble(msg, is_first_load=True)

        self.topbar.set_agent(self.agent)
        # self.scroll_to_end()

    def clear_bubbles(self):
        while self.chat_bubbles:
            bubble = self.chat_bubbles.pop()
            self.chat_scroll_layout.removeWidget(bubble)
            bubble.deleteLater()

    def on_button_click(self):
        self.send_message(self.main.message_text.toPlainText(), clear_input=True)

    def send_message(self, message, role='user', clear_input=False):
        global PIN_STATE
        try:
            new_msg = self.agent.save_message(role, message)
        except Exception as e:
            # show error message box
            old_pin_state = PIN_STATE
            PIN_STATE = True
            QMessageBox.critical(self, "Error", "OpenAI API Error: " + str(e))
            PIN_STATE = old_pin_state
            return

        if not new_msg:
            return

        auto_title = self.agent.config.get('context.auto_title', True)
        if not self.agent.context.message_history.count() == 1:
            auto_title = False

        if clear_input:
            # QTimer.singleShot(1, self.main.message_text.clear)
            QTimer.singleShot(1, self.main.message_text.clear)
            self.main.message_text.setFixedHeight(51)
            self.main.send_button.setFixedHeight(51)

        if role == 'user':
            self.main.new_bubble_signal.emit({'id': new_msg.id, 'role': 'user', 'content': new_msg.content})
            # self.scroll_to_end()
            # set a single shot timer to scroll to end as late as possible
            # update the ui before scrolling
            QApplication.processEvents()
            self.scroll_to_end()
            QApplication.processEvents()

        for key, chunk in self.agent.receive(stream=True):
            if key == 'assistant' or key == 'message':
                self.main.new_sentence_signal.emit(chunk)
                self.scroll_to_end()
            else:
                break

        self.load_new_code_bubbles()

        if auto_title:
            self.agent.context.generate_title()

    @Slot(dict)
    def insert_bubble(self, message=None, is_first_load=False):
        viewport = self
        msg_role = message['role']

        if msg_role == 'user':
            bubble = self.MessageBubbleUser(message['id'], message['content'], viewport, role=msg_role, parent=self)
        elif msg_role == 'code':
            bubble = self.MessageBubbleCode(message['id'], message['content'], viewport, role=msg_role, parent=self, start_timer=not is_first_load)
        else:
            bubble = self.MessageBubbleBase(message['id'], message['content'], viewport, role=msg_role, parent=self)

        self.chat_bubbles.append(bubble)
        count = len(self.chat_bubbles)

        if msg_role == 'assistant':
            self.last_assistant_bubble = bubble
        else:
            self.last_assistant_bubble = None

        self.chat_scroll_layout.insertWidget(count - 1, bubble)

        return bubble

    @Slot(str)
    def new_sentence(self, sentence):
        if self.last_assistant_bubble is None:
            self.main.new_bubble_signal.emit({'id': -1, 'role': 'assistant', 'content': sentence})
        else:
            self.last_assistant_bubble.append_text(sentence)

    def scroll_to_end(self):
        QCoreApplication.processEvents()  # process GUI events to update content size
        scrollbar = self.main.page_chat.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum() + 20)
        # QCoreApplication.processEvents()

    def goto_context(self, context_id):
        from agent.base import Agent
        self.main.page_chat.agent = Agent(agent_id=None, context_id=context_id)
        self.main.page_chat.load_bubbles()

class SideBar(QWidget):
    def __init__(self, main):
        super().__init__(parent=main)
        self.main = main
        self.setObjectName("SideBarWidget")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setProperty("class", "sidebar")

        self.btn_new_context = self.SideBar_NewContext(self)
        self.btn_settings = self.SideBar_Settings(main=main)
        self.btn_agents = self.SideBar_Agents(main=main)
        self.btn_contexts = self.SideBar_Contexts(main=main)
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Create a button group and add buttons to it
        self.button_group = QButtonGroup(self)
        self.button_group.addButton(self.btn_new_context, 0)
        self.button_group.addButton(self.btn_settings, 1)
        self.button_group.addButton(self.btn_agents, 2)
        self.button_group.addButton(self.btn_contexts, 3)  # 1

        self.title_bar = TitleButtonBar(self.main)
        self.layout.addWidget(self.title_bar)
        self.layout.addStretch(1)

        self.layout.addWidget(self.btn_settings)
        self.layout.addWidget(self.btn_agents)
        self.layout.addWidget(self.btn_contexts)
        self.layout.addWidget(self.btn_new_context)

    def update_buttons(self):
        is_current_chat = self.main.content.currentWidget() == self.main.page_chat
        icon_iden = 'chat' if not is_current_chat else 'new-large'
        icon = QIcon(QPixmap(f"./utils/resources/icon-{icon_iden}.png"))
        self.btn_new_context.setIcon(icon)

    class SideBar_NewContext(QPushButton):
        def __init__(self, parent):
            super().__init__(parent=parent, icon=QIcon())
            self.parent = parent
            self.main = parent.main
            self.clicked.connect(self.new_context)
            self.icon = QIcon(QPixmap("./utils/resources/icon-new-large.png"))
            self.setIcon(self.icon)
            self.setToolTip("New context")
            self.setFixedSize(50, 50)
            self.setIconSize(QSize(50, 50))
            self.setCheckable(True)
            self.setObjectName("homebutton")

        def new_context(self):
            is_current_widget = self.main.content.currentWidget() == self.main.page_chat
            if is_current_widget:
                self.main.page_chat.agent.context.new_context()
                self.main.page_chat.load_bubbles()
            else:
                self.load_chat()

        def load_chat(self):
            self.main.content.setCurrentWidget(self.main.page_chat)
            self.main.page_chat.load_bubbles()

    class SideBar_Settings(QPushButton):
        def __init__(self, main):
            super().__init__(parent=main, icon=QIcon())
            self.main = main
            self.clicked.connect(self.open_settins)
            self.icon = QIcon(QPixmap("./utils/resources/icon-settings.png"))
            self.setIcon(self.icon)
            self.setToolTip("Settings")
            self.setFixedSize(50, 50)
            self.setIconSize(QSize(50, 50))
            self.setCheckable(True)

        def open_settins(self):
            self.main.content.setCurrentWidget(self.main.page_settings)

    class SideBar_Agents(QPushButton):
        def __init__(self, main):
            super().__init__(parent=main, icon=QIcon())
            self.main = main
            self.clicked.connect(self.open_settins)
            self.icon = QIcon(QPixmap("./utils/resources/icon-agent.png"))
            self.setIcon(self.icon)
            self.setToolTip("Agents")
            self.setFixedSize(50, 50)
            self.setIconSize(QSize(50, 50))
            self.setCheckable(True)

        def open_settins(self):
            self.main.content.setCurrentWidget(self.main.page_agents)

    class SideBar_Contexts(QPushButton):
        def __init__(self, main):
            super().__init__(parent=main, icon=QIcon())
            self.main = main
            self.clicked.connect(self.open_contexts)
            self.icon = QIcon(QPixmap("./utils/resources/icon-contexts.png"))
            self.setIcon(self.icon)
            self.setToolTip("Contexts")
            self.setFixedSize(50, 50)
            self.setIconSize(QSize(50, 50))
            self.setCheckable(True)

        def open_contexts(self):
            self.main.content.setCurrentWidget(self.main.page_contexts)


# class TopBar(QWidget):
#     def __init__(self, parent=None):
#         super().__init__(parent=parent)
#         self.setFixedHeight(50)


# class ButtonBar(QWidget):
#     def __init__(self, parent=None):
#         super().__init__(parent=parent)
#         self.setObjectName("TitleBarWidget")
#         self.setAttribute(Qt.WA_StyledBackground, True)
#         self.setFixedHeight(20)
#         sizePolicy = QSizePolicy()
#         sizePolicy.setHorizontalPolicy(QSizePolicy.Policy.Fixed)
#
#         self.btn_personality = self.ButtonBar_Personality(parent=self)
#         self.btn_jailbreak = self.ButtonBar_Jailbreak(parent=self)
#         self.btn_interpreter = self.ButtonBar_OpenInterpreter(parent=self)
#         # self.layout.addWidget(self.minimizeButton)
#         # self.layout.addWidget(self.closeButton)
#         self.layout = QHBoxLayout(self)
#         self.layout.setSpacing(0)
#         self.layout.setContentsMargins(0, 0, 0, 0)
#         self.layout.addStretch(1)
#         self.layout.addWidget(self.btn_interpreter)
#         self.layout.addWidget(self.btn_personality)
#         self.layout.addWidget(self.btn_jailbreak)
#         # self.layout.addWidget(self.closeButton)
#         self.setMouseTracking(True)
#         self._pressed = False
#         self._cpos = None
#         # make the title bar transparent
#         self.setAttribute(Qt.WA_TranslucentBackground, True)
#
#     class ButtonBar_Personality(QPushButton):
#         def __init__(self, parent=None):
#             super().__init__(parent=parent, icon=QIcon())
#             self.setFixedHeight(20)
#             self.setFixedWidth(20)
#             self.clicked.connect(self.toggle_personality)
#             self.icon = QIcon(QPixmap("./utils/resources/icon-drama-on.png"))
#             self.setIcon(self.icon)
#             self.setToolTip("Personality")
#
#         def toggle_personality(self):
#             global PERSONALITY_STATE
#             PERSONALITY_STATE = not PERSONALITY_STATE
#             icon_iden = "on" if PERSONALITY_STATE else "off"
#             icon_file = f"./utils/resources/icon-drama-{icon_iden}.png"
#             self.icon = QIcon(QPixmap(icon_file))
#             self.setIcon(self.icon)
#
#     class ButtonBar_Jailbreak(QPushButton):
#         def __init__(self, parent=None):
#             super().__init__(parent=parent, icon=QIcon())
#             self.setFixedHeight(20)
#             self.setFixedWidth(20)
#             self.clicked.connect(self.toggle_personality)
#             self.icon = QIcon(QPixmap("./utils/resources/icon-jailbreak-on.png"))
#             self.setIcon(self.icon)
#             self.setToolTip("Jailbreak")
#
#         def toggle_personality(self):
#             global PERSONALITY_STATE
#             PERSONALITY_STATE = not PERSONALITY_STATE
#             icon_iden = "on" if PERSONALITY_STATE else "off"
#             icon_file = f"./utils/resources/icon-jailbreak-{icon_iden}.png"
#             self.icon = QIcon(QPixmap(icon_file))
#             self.setIcon(self.icon)
#
#     class ButtonBar_OpenInterpreter(QPushButton):
#         def __init__(self, parent=None):
#             super().__init__(parent=parent, icon=QIcon())
#             self.setFixedHeight(20)
#             self.setFixedWidth(20)
#             self.clicked.connect(self.toggle_openinterpreter)
#             self.icon = QIcon(QPixmap("./utils/resources/icon-interpreter-on.png"))
#             self.setIcon(self.icon)
#             self.setToolTip("Open Interpreter")
#
#         def toggle_openinterpreter(self):
#             global OPEN_INTERPRETER_STATE
#             # 3 WAY TOGGLE
#             OPEN_INTERPRETER_STATE = ((OPEN_INTERPRETER_STATE + 1 + 1) % 3) - 1
#             icon_iden = "on" if OPEN_INTERPRETER_STATE == 0 else "forced" if OPEN_INTERPRETER_STATE == 1 else "off"
#             icon_file = f"./utils/resources/icon-interpreter-{icon_iden}.png"
#             self.icon = QIcon(QPixmap(icon_file))
#             self.setIcon(self.icon)


class MessageText(QTextEdit):
    enterPressed = Signal()

    def __init__(self, main=None):
        super().__init__(parent=None)
        self.parent = main
        self.agent = main.page_chat.agent
        self.setCursor(QCursor(Qt.PointingHandCursor))
        text_size = config.get_value('display.text_size')
        text_font = config.get_value('display.text_font')
        self.font = QFont()  # text_font, text_size)
        if text_font != '': self.font.setFamily(text_font)
        self.font.setPointSize(text_size)
        self.setCurrentFont(self.font)

    def keyPressEvent(self, event):
        combo = event.keyCombination()
        key = combo.key()
        mod = combo.keyboardModifiers()

        # Check for Ctrl + B key combination
        if key == Qt.Key.Key_B and mod == Qt.KeyboardModifier.ControlModifier:
            # Insert the code block where the cursor is
            cursor = self.textCursor()
            cursor.insertText("```\n\n```")  # Inserting with new lines between to create a space for the code
            cursor.movePosition(QTextCursor.PreviousBlock, QTextCursor.MoveAnchor, 1)  # Move cursor inside the code block
            self.setTextCursor(cursor)
            self.setFixedSize(self.sizeHint())
            return  # We handle the event, no need to pass it to the base class

        if key == Qt.Key.Key_Enter or key == Qt.Key.Key_Return:
            if mod == Qt.KeyboardModifier.ShiftModifier:
                event.setModifiers(Qt.KeyboardModifier.NoModifier)

                se = super().keyPressEvent(event)
                self.setFixedSize(self.sizeHint())
                self.parent.sync_send_button_size()
                return se
            else:
                if self.toPlainText().strip() == '':
                    return
                return self.enterPressed.emit()

        se = super().keyPressEvent(event)
        self.setFixedSize(self.sizeHint())
        self.parent.sync_send_button_size()
        return se

    def sizeHint(self):
        # Use QTextDocument for more accurate text measurements
        doc = QTextDocument()
        doc.setDefaultFont(self.font)
        doc.setPlainText(self.toPlainText())

        # Assuming you want to keep a minimum height for 3 lines of text
        min_height_lines = 2

        # Calculate the required width and height
        text_rect = doc.documentLayout().documentSize()
        width = self.width()
        font_height = QFontMetrics(self.font).height()
        num_lines = max(min_height_lines, text_rect.height() / font_height)

        # Calculate height based on the number of lines
        height = int(font_height * num_lines)
        height = min(height, 338)
        # height = min(height, )

        return QSize(width, height)

    files = []

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            self.files.append(url.toLocalFile())
            # insert text where cursor is

        event.accept()

    def insertFromMimeData(self, source: QMimeData):
        """
        Reimplemented from QTextEdit.insertFromMimeData().
        Inserts plain text data from the MIME data source.
        """
        # Check if the MIME data source has text
        if source.hasText():
            # Get the plain text from the source
            text = source.text()

            # Insert the plain text at the current cursor position
            self.insertPlainText(text)
        else:
            # If the source does not contain text, call the base class implementation
            super().insertFromMimeData(source)


class SendButton(QPushButton):
    def __init__(self, text, msgbox, parent=None):
        super().__init__(text, parent=parent)
        self._parent = parent
        self.msgbox = msgbox
        self.icon = QIcon(QPixmap("./utils/resources/icon-send.png"))
        self.setIcon(self.icon)

    def minimumSizeHint(self):
        return self.sizeHint()

    def sizeHint(self):
        height = self._parent.message_text.height()
        width = 70
        return QSize(width, height)


class Main(QMainWindow):
    new_bubble_signal = Signal(dict)
    new_sentence_signal = Signal(str)

    mouseEntered = Signal()
    mouseLeft = Signal()

    def check_db(self):
        # Check if the database is available
        while not check_database():
            # If not, show a QFileDialog to get the database location
            sql.db_path, _ = QFileDialog.getOpenFileName(None, "Open Database", "", "Database Files (*.db);;All Files (*)")

            if not sql.db_path:
                QMessageBox.critical(None, "Error", "Database not selected. Application will exit.")
                return

            # Set the database location in the agent
            config.set_value('system.db_path', sql.db_path)

    def set_stylesheet(self):
        QApplication.instance().setStyleSheet(get_stylesheet())

    def __init__(self):  # , base_agent=None):
        super().__init__()
        self.check_db()

        self.leave_timer = QTimer(self)
        self.leave_timer.setSingleShot(True)
        self.leave_timer.timeout.connect(self.collapse)

        self.setWindowTitle('AgentPilot')
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setWindowIcon(QIcon('./utils/resources/icon.png'))
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.central = QWidget()
        self.central.setProperty("class", "central")
        self._layout = QVBoxLayout(self.central)
        self.setMouseTracking(True)

        self.sidebar = SideBar(self)

        self.content = QStackedWidget(self)
        self.page_chat = Page_Chat(self)
        self.page_settings = Page_Settings(self)
        self.page_agents = Page_Agents(self)
        self.page_contexts = Page_Contexts(self)
        self.content.addWidget(self.page_chat)
        self.content.addWidget(self.page_settings)
        self.content.addWidget(self.page_agents)
        self.content.addWidget(self.page_contexts)
        self.content.currentChanged.connect(self.load_page)

        # self.page_chat.agent = base_agent

        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_layout.setSpacing(0)
        self.sidebar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        # Horizontal layout for content and sidebar
        hlayout = QHBoxLayout()
        hlayout.addWidget(self.content)
        hlayout.addWidget(self.sidebar)
        hlayout.setSpacing(0)

        self.content_container = QWidget()
        self.content_container.setLayout(hlayout)

        # self.sidebar_layout.addStretch(1)

        # Adding the scroll area to the main layout
        self._layout.addWidget(self.content_container)

        # Message text and send button
        # self.button_bar = ButtonBar()
        self.message_text = MessageText(main=self)
        self.message_text.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.message_text.setFixedHeight(46)
        self.message_text.setProperty("class", "msgbox")
        self.send_button = SendButton('', self.message_text, self)
        self.send_button.setFixedSize(70, 46)
        self.send_button.setProperty("class", "send")

        # Horizontal layout for message text and send button
        self.hlayout = QHBoxLayout()
        self.hlayout.addWidget(self.message_text)
        self.hlayout.addWidget(self.send_button)
        # self.spacer = QSpacerItem(0, 0)
        self.hlayout.setSpacing(0)
        # Button bar should not stretch vertically

        # Vertical layout for button bar and input layout
        input_layout = QVBoxLayout()
        # input_layout.addWidget(self.button_bar)
        input_layout.addLayout(self.hlayout)

        # Create a QWidget to act as a container for the input widgets and button bar
        input_container = QWidget()
        input_container.setLayout(input_layout)

        # Adding input layout to the main layout
        self._layout.addWidget(input_container)
        self._layout.setSpacing(1)

        self.setCentralWidget(self.central)
        self.send_button.clicked.connect(self.page_chat.on_button_click)
        self.message_text.enterPressed.connect(self.page_chat.on_button_click)

        self.new_bubble_signal.connect(self.page_chat.insert_bubble)
        self.new_sentence_signal.connect(self.page_chat.new_sentence)
        self.oldPosition = None
        self.expanded = False

        self.show()
        self.page_chat.load()

    def sync_send_button_size(self):
        self.send_button.setFixedHeight(self.message_text.height())

    def is_bottom_corner(self):
        screen_geo = QGuiApplication.primaryScreen().geometry() # get screen geometry
        win_geo = self.geometry()  # get window geometry
        win_x = win_geo.x()
        win_y = win_geo.y()
        win_width = win_geo.width()
        win_height = win_geo.height()
        screen_width = screen_geo.width()
        screen_height = screen_geo.height()
        win_right = win_x + win_width >= screen_width
        win_bottom = win_y + win_height >= screen_height
        is_right_corner = win_right and win_bottom
        return is_right_corner

    def collapse(self):
        global PIN_STATE
        if PIN_STATE: return
        if not self.expanded: return

        if self.is_bottom_corner():
            self.message_text.hide()
            self.send_button.hide()
            self.change_width(50)

        self.expanded = False
        self.content_container.hide()
        QApplication.processEvents()
        self.change_height(100)

    def expand(self):
        if self.expanded: return
        self.expanded = True
        self.change_height(750)
        self.change_width(700)
        self.content_container.show()
        self.message_text.show()
        self.send_button.show()
        # self.button_bar.show()

    def mousePressEvent(self, event):
        self.oldPosition = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.oldPosition is None: return
        delta = QPoint(event.globalPosition().toPoint() - self.oldPosition)
        self.move(self.x() + delta.x(), self.y() + delta.y())
        self.oldPosition = event.globalPosition().toPoint()

    def enterEvent(self, event):
        self.leave_timer.stop()
        self.expand()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.leave_timer.start(1000)
        super().leaveEvent(event)

    def change_height(self, height):
        old_height = self.height()
        self.setFixedHeight(height)
        self.move(self.x(), self.y() - (height - old_height))

    def change_width(self, width):
        old_width = self.width()
        self.setFixedWidth(width)
        self.move(self.x() - (width - old_width), self.y())

    def sizeHint(self):
        return QSize(600, 100)

    def load_page(self, index):
        self.sidebar.update_buttons()
        self.content.widget(index).load()
        # if page == self.page_agents:
        #     self.page_agents.load()
        # elif page == self.page_contexts:
        #     self.page_contexts.load()
        # elif page == self.page_settings:
        #     self.page_settings.load()


class NoWheelSpinBox(QSpinBox):
    """A SpinBox that does not react to mouse wheel events."""

    def wheelEvent(self, event):
        event.ignore()

class NoWheelComboBox(QComboBox):
    """A SpinBox that does not react to mouse wheel events."""

    def wheelEvent(self, event):
        event.ignore()

def create_checkbox(self, label, initial_value):
    cb = QCheckBox(label, self)
    cb.setChecked(initial_value)
    return cb

def create_lineedit(self, initial_value=''):
    le = QLineEdit(self)
    le.setText(str(initial_value))
    return le

def create_combobox(self, items, initial_value):
    cb = QComboBox(self)
    for item in items:
        cb.addItem(item)
    cb.setCurrentText(initial_value)
    return cb

def create_folder_button(self, initial_value):
    btn = QPushButton("Select Folder", self)
    btn.clicked.connect(lambda: self.select_folder(btn, initial_value))
    return btn

def select_folder(self, button, initial_value):
    folder = QFileDialog.getExistingDirectory(self, "Select Folder", initial_value)
    folder.setStyleSheet("color: white;")
    if folder:
        # Store the folder to config or use it as you need
        pass


class GUI:
    def __init__(self):
        pass

    def run(self):
        app = QApplication(sys.argv)
        app.setStyleSheet(get_stylesheet())
        m = Main()  # self.agent)
        m.expand()
        app.exec()
