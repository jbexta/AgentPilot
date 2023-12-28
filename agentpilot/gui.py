import importlib
import inspect
import json
import os
import sys
from contextlib import contextmanager
from functools import partial
from sqlite3 import IntegrityError

from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtWidgets import *
from PySide6.QtCore import QThreadPool, Signal, QSize, QEvent, QTimer, QMargins, QRect, QRunnable, Slot, QMimeData, \
    QPoint, QPointF
from PySide6.QtGui import QPixmap, QPalette, QColor, QIcon, QFont, QPainter, QPainterPath, QTextCursor, QIntValidator, \
    QTextOption, QTextDocument, QFontMetrics, QGuiApplication, Qt, QCursor, QFontDatabase, QBrush, \
    QPen, QKeyEvent, QDoubleValidator

import agentpilot.plugins.openinterpreter.src.core.core
# from agentpilot.plugins.openinterpreter.src.core.core import run_code

from agentpilot.utils.filesystem import simplify_path
from agentpilot.utils.helpers import create_circular_pixmap, path_to_pixmap
from agentpilot.utils.sql_upgrade import upgrade_script, versions
from agentpilot.utils import sql, api, config, resources_rc
from agentpilot.utils.apis import llm
from agentpilot.utils.plugin import get_plugin_agent_class

import mistune

from agentpilot.context.messages import Message
from agentpilot.system.base import SystemManager

os.environ["QT_OPENGL"] = "software"


def display_messagebox(icon, text, title, buttons=(QMessageBox.Ok)):
    msg = QMessageBox()
    msg.setIcon(icon)
    msg.setText(text)
    msg.setWindowTitle(title)
    msg.setStandardButtons(buttons)
    msg.setWindowFlags(msg.windowFlags() | Qt.WindowStaysOnTopHint)
    return msg.exec_()


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


# DEV_API_KEY = None
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
    background-color: #0dffffff;
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
    background-color: #0dffffff;
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
    background-color: #0dffffff;
    color: {TEXT_COLOR};
}}
QPushButton:checked {{
    background-color: #0dffffff;
    border-radius: 3px;
}}
QPushButton:checked:hover {{
    background-color: #0dffffff;
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
    background: {TEXT_COLOR} url(":/resources/icon-tick.svg") no-repeat center center;
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
    border-bottom-right-radius: 0px;
}}
QTextEdit.user {{
    background-color: {USER_BUBBLE_BG_COLOR};
    font-size: {TEXT_SIZE}px; 
    border-radius: 12px;
    border-bottom-left-radius: 0px;
    /* border-top-right-radius: 0px;*/
}}
QTextEdit.assistant {{
    background-color: {ASSISTANT_BUBBLE_BG_COLOR};
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
QTabBar::tab {{
    background: {PRIMARY_COLOR};
    border: 1px solid {SECONDARY_COLOR};
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 5px;
    min-width: 50px;
    color: {TEXT_COLOR};
}}
QTabBar::tab:selected, QTabBar::tab:hover {{
    background: {SECONDARY_COLOR};
}}
QTabBar::tab:selected {{
    border-bottom-color: transparent;
}}
QTabWidget::pane {{
    border: 0px;
    top: -1px;
}}
QComboBox {{
    color: {TEXT_COLOR};
}}
QComboBox QAbstractItemView {{
    border: 0px;
    selection-background-color: lightgray; /* Background color for hovered/selected item */
    background-color: {SECONDARY_COLOR}; /* Background color for dropdown */
    color: {TEXT_COLOR};
}}
QScrollBar {{
    width: 0px;
}}
QListWidget::item {{
    color: {TEXT_COLOR};
}}
QHeaderView::section {{
    background-color: {PRIMARY_COLOR};
    color: {TEXT_COLOR};
    border: 0px;
}}
"""


class TitleButtonBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.parent = parent
        self.main = parent.main
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
            self.icon = QIcon(QPixmap(":/resources/icon-pin-on.png"))
            self.setIcon(self.icon)

        def toggle_pin(self):
            global PIN_STATE
            PIN_STATE = not PIN_STATE
            icon_iden = "on" if PIN_STATE else "off"
            icon_file = f":/resources/icon-pin-{icon_iden}.png"
            self.icon = QIcon(QPixmap(icon_file))
            self.setIcon(self.icon)

    class TitleBarButtonMin(QPushButton):
        def __init__(self, parent=None):
            super().__init__(parent=parent)
            self.parent = parent
            self.setFixedHeight(20)
            self.setFixedWidth(20)
            self.clicked.connect(self.window_action)
            self.icon = QIcon(QPixmap(":/resources/minus.png"))
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
            self.icon = QIcon(QPixmap(":/resources/close.png"))
            self.setIcon(self.icon)

        def closeApp(self):
            self.parent().main.window().close()


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
        palette.setColor(QPalette.Highlight, '#0dffffff')
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))  # Setting text color to white
        palette.setColor(QPalette.Text, QColor(TEXT_COLOR))  # Setting unselected text color to purple
        self.setPalette(palette)

        # Set the horizontal header properties (column headers)
        horizontalHeader = self.horizontalHeader()
        # Use a style sheet to change the background color of the column headers
        horizontalHeader.setStyleSheet(
            "QHeaderView::section {"
            f"background-color: {PRIMARY_COLOR};"  # Red background
            "color: #ffffff;"  # White text color
            "padding-left: 4px;"  # Padding from the left edge
            "}"
        )


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


class CComboBox(QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_pin_state = None

        self.setFixedWidth(150)

    def showPopup(self):
        global PIN_STATE
        self.current_pin_state = PIN_STATE
        PIN_STATE = True
        super().showPopup()

    def hidePopup(self):
        global PIN_STATE
        if self.current_pin_state is None:
            self.current_pin_state = PIN_STATE
        PIN_STATE = self.current_pin_state
        super().hidePopup()


class PluginComboBox(CComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setItemDelegate(AlignDelegate(self))
        self.setFixedWidth(150)
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
        # # get selected text
        # selected_text = self.currentText()
        # # get id of selected text
        # selected_id = self.findText(selected_text)

        self.clear()
        models = sql.get_results("SELECT alias, model_name FROM models ORDER BY api_id, alias")
        if self.first_item:
            self.addItem(self.first_item, 0)
        try:
            for model in models:
                self.addItem(model[0], model[1])
        except Exception as e:
            print(e)

        # # set selected text
        # self.setCurrentIndex(selected_id)


class APIComboBox(CComboBox):
    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)

        self.load()

    def load(self):
        self.clear()
        models = sql.get_results("SELECT name, id FROM apis")
        if self.first_item:
            self.addItem(self.first_item, 0)
        for model in models:
            self.addItem(model[0], model[1])


class RoleComboBox(CComboBox):
    def __init__(self, *args, **kwargs):
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)

        self.load()

    def load(self):
        self.clear()
        models = sql.get_results("SELECT name, id FROM roles")
        if self.first_item:
            self.addItem(self.first_item, 0)
        for model in models:
            self.addItem(model[0].title(), model[1])


class AlignDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        option.displayAlignment = Qt.AlignCenter
        super(AlignDelegate, self).paint(painter, option, index)


class FixedUserBubble(QGraphicsEllipseItem):
    def __init__(self, parent):
        super(FixedUserBubble, self).__init__(0, 0, 50, 50)
        self.id = 0
        self.parent = parent

        self.setPos(-42, 75)

        pixmap = QPixmap(":/resources/icon-agent.png")
        self.setBrush(QBrush(pixmap.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)))

        # set border color
        self.setPen(QPen(QColor(BORDER_COLOR), 2))

        self.output_point = ConnectionPoint(self, False)
        self.output_point.setPos(self.rect().width() - 4, self.rect().height() / 2)

        self.setAcceptHoverEvents(True)

    def hoverMoveEvent(self, event):
        # Check if the mouse is within 20 pixels of the output point
        if self.output_point.contains(event.pos() - self.output_point.pos()):
            self.output_point.setHighlighted(True)
        else:
            self.output_point.setHighlighted(False)
        super(FixedUserBubble, self).hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.output_point.setHighlighted(False)
        super(FixedUserBubble, self).hoverLeaveEvent(event)


class DraggableAgent(QGraphicsEllipseItem):
    def __init__(self, id, parent, x, y, member_inp_str, member_type_str, agent_config):
        super(DraggableAgent, self).__init__(0, 0, 50, 50)
        pen = QPen(QColor('transparent'))
        self.setPen(pen)

        self.id = id
        self.parent = parent

        if member_type_str:
            member_inp_str = '0' if member_inp_str == 'NULL' else member_inp_str  # todo dirty
        self.member_inputs = dict(
            zip([int(x) for x in member_inp_str.split(',')], member_type_str.split(','))) if member_type_str else {}

        self.setPos(x, y)

        agent_config = json.loads(agent_config)
        hide_responses = agent_config.get('group.hide_responses', False)
        agent_avatar_path = agent_config.get('general.avatar_path', '')
        opacity = 0.2 if hide_responses else 1
        diameter = 50
        pixmap = path_to_pixmap(agent_avatar_path, opacity=opacity, diameter=diameter)

        self.setBrush(QBrush(pixmap.scaled(diameter, diameter)))

        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)

        self.input_point = ConnectionPoint(self, True)
        self.output_point = ConnectionPoint(self, False)
        self.input_point.setPos(0, self.rect().height() / 2)
        self.output_point.setPos(self.rect().width() - 4, self.rect().height() / 2)

        self.setAcceptHoverEvents(True)

        self.close_btn = self.DeleteButton(self, id)
        self.hide_btn = self.HideButton(self, id)

    def mouseReleaseEvent(self, event):
        super(DraggableAgent, self).mouseReleaseEvent(event)
        new_loc_x = self.x()
        new_loc_y = self.y()
        sql.execute('UPDATE contexts_members SET loc_x = ?, loc_y = ? WHERE id = ?', (new_loc_x, new_loc_y, self.id))

    def mouseMoveEvent(self, event):
        if self.output_point.contains(event.pos() - self.output_point.pos()):
            return

        if self.parent.new_line:
            return

        super(DraggableAgent, self).mouseMoveEvent(event)
        self.close_btn.hide()
        self.hide_btn.hide()
        for line in self.parent.lines.values():
            line.updatePosition()

    def hoverMoveEvent(self, event):
        # Check if the mouse is within 20 pixels of the output point
        if self.output_point.contains(event.pos() - self.output_point.pos()):
            self.output_point.setHighlighted(True)
        else:
            self.output_point.setHighlighted(False)
        super(DraggableAgent, self).hoverMoveEvent(event)

    def hoverEnterEvent(self, event):
        # move close button to top right of agent
        pos = self.pos()
        self.close_btn.move(pos.x() + self.rect().width() + 40, pos.y() + 15)
        self.close_btn.show()
        self.hide_btn.move(pos.x() + self.rect().width() + 40, pos.y() + 55)
        self.hide_btn.show()
        super(DraggableAgent, self).hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.output_point.setHighlighted(False)
        if not self.isUnderMouse():
            self.close_btn.hide()
            self.hide_btn.hide()
        super(DraggableAgent, self).hoverLeaveEvent(event)

    class DeleteButton(QPushButton):
        def __init__(self, parent, id):
            super().__init__(parent=parent.parent)
            self.parent = parent
            self.id = id
            self.setFixedSize(14, 14)
            self.setText('X')
            # set text to bold
            font = self.font()
            font.setBold(True)
            self.setFont(font)
            # set color = red
            self.setStyleSheet("background-color: transparent; color: darkred;")
            # self.move(self.x() + self.rect().width() + 10, self.y() + 10)
            self.hide()

            # on mouse clicked
            self.clicked.connect(self.delete_agent)

        def leaveEvent(self, event):
            self.parent.close_btn.hide()
            self.parent.hide_btn.hide()
            super().leaveEvent(event)

        def delete_agent(self):
            self.parent.parent.delete_ids([self.id])

    class HideButton(QPushButton):
        def __init__(self, parent, id):
            super().__init__(parent=parent.parent)
            self.parent = parent
            self.id = id
            self.setFixedSize(14, 14)
            self.setIcon(QIcon(':/resources/icon-hide.png'))
            # set text to bold
            font = self.font()
            font.setBold(True)
            self.setFont(font)
            self.setStyleSheet("background-color: transparent; color: darkred;")
            self.hide()

            # on mouse clicked
            self.clicked.connect(self.hide_agent)

        def hide_agent(self):
            self.parent.parent.select_ids([self.id])
            qcheckbox = self.parent.parent.agent_settings.page_group.hide_responses
            qcheckbox.setChecked(not qcheckbox.isChecked())
            # reload the agents
            self.parent.parent.load()
            # = not self.parent.parent.agent_settings.page_group.hide_responses

        def leaveEvent(self, event):
            self.parent.close_btn.hide()
            self.parent.hide_btn.hide()
            super().leaveEvent(event)


class TemporaryConnectionLine(QGraphicsPathItem):
    def __init__(self, parent, agent):
        super(TemporaryConnectionLine, self).__init__()
        self.parent = parent
        self.input_member_id = agent.id
        self.output_point = agent.output_point
        self.setPen(QPen(Qt.darkGray, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        self.temp_end_point = self.output_point.scenePos()
        self.updatePath()

    def updatePath(self):
        path = QPainterPath(self.output_point.scenePos())
        ctrl_point1 = self.output_point.scenePos() + QPointF(50, 0)
        ctrl_point2 = self.temp_end_point - QPointF(50, 0)
        path.cubicTo(ctrl_point1, ctrl_point2, self.temp_end_point)
        self.setPath(path)

    def updateEndPoint(self, end_point):
        self.temp_end_point = end_point
        self.updatePath()

    def attach_to_member(self, member_id):
        self.parent.add_input(self.input_member_id, member_id)


class ConnectionLine(QGraphicsPathItem):
    def __init__(self, key, start_point, end_point, input_type=0):
        super(ConnectionLine, self).__init__()
        self.key = key
        self.input_type = int(input_type)
        self.start_point = start_point
        self.end_point = end_point
        self.setFlag(QGraphicsItem.ItemIsSelectable)

        self.color = Qt.darkGray

        path = QPainterPath(start_point.scenePos())

        ctrl_point1 = start_point.scenePos() - QPointF(50, 0)  # Control point 1 right of start
        ctrl_point2 = end_point.scenePos() + QPointF(50, 0)  # Control point 2 left of end
        path.cubicTo(ctrl_point1, ctrl_point2, end_point.scenePos())

        self.setPath(path)
        self.setPen(QPen(Qt.darkGray, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        self.setZValue(-1)

        self.setAcceptHoverEvents(True)

    def paint(self, painter, option, widget):
        line_width = 5 if self.isSelected() else 3
        current_pen = self.pen()
        current_pen.setWidth(line_width)
        # set to a dashed line if input type is 1
        if self.input_type == 1:
            current_pen.setStyle(Qt.DashLine)
        painter.setPen(current_pen)
        painter.drawPath(self.path())

    def updatePosition(self):
        path = QPainterPath(self.start_point.scenePos())
        ctrl_point1 = self.start_point.scenePos() - QPointF(50, 0)
        ctrl_point2 = self.end_point.scenePos() + QPointF(50, 0)
        path.cubicTo(ctrl_point1, ctrl_point2, self.end_point.scenePos())
        self.setPath(path)
        self.scene().update(self.scene().sceneRect())


class TemporaryInsertableAgent(QGraphicsEllipseItem):
    def __init__(self, parent, agent_id, agent_conf, pos):
        super(TemporaryInsertableAgent, self).__init__(0, 0, 50, 50)
        self.parent = parent
        self.id = agent_id
        agent_avatar_path = agent_conf.get('general.avatar_path', '')
        pixmap = path_to_pixmap(agent_avatar_path, diameter=50)
        self.setBrush(QBrush(pixmap.scaled(50, 50)))
        self.setCentredPos(pos)

    def setCentredPos(self, pos):
        self.setPos(pos.x() - self.rect().width() / 2, pos.y() - self.rect().height() / 2)


class ConnectionPoint(QGraphicsEllipseItem):
    def __init__(self, parent, is_input):
        radius = 2
        super(ConnectionPoint, self).__init__(0, 0, 2 * radius, 2 * radius, parent)
        self.is_input = is_input
        self.setBrush(QBrush(Qt.darkGray if is_input else Qt.darkRed))
        self.connections = []

    def setHighlighted(self, highlighted):
        if highlighted:
            self.setBrush(QBrush(Qt.red))
        else:
            self.setBrush(QBrush(Qt.black))

    def contains(self, point):
        distance = (point - self.rect().center()).manhattanLength()
        return distance <= 12


class CustomGraphicsView(QGraphicsView):
    def __init__(self, scene, parent):
        super(CustomGraphicsView, self).__init__(scene, parent)
        self.setMouseTracking(True)
        self.setRenderHint(QPainter.Antialiasing)
        self.parent = parent

    def mouseMoveEvent(self, event):
        # point = event.pos()
        if self.parent.new_line:
            self.parent.new_line.updateEndPoint(self.mapToScene(event.pos()))
            if self.scene():
                self.scene().update()
            self.update()
        if self.parent.new_agent:
            self.parent.new_agent.setCentredPos(self.mapToScene(event.pos()))
            if self.scene():
                self.scene().update()
            self.update()

        super(CustomGraphicsView, self).mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:  # todo - refactor
            if self.parent.new_line:
                # Remove the temporary line from the scene and delete it
                self.scene().removeItem(self.parent.new_line)
                self.parent.new_line = None
                self.update()
            if self.parent.new_agent:
                # Remove the temporary line from the scene and delete it
                self.scene().removeItem(self.parent.new_agent)
                self.parent.new_agent = None
                self.update()
        elif event.key() == Qt.Key_Delete:
            if self.parent.new_line:
                # Remove the temporary line from the scene and delete it
                self.scene().removeItem(self.parent.new_line)
                self.parent.new_line = None
                self.update()
                return
            if self.parent.new_agent:
                # Remove the temporary line from the scene and delete it
                self.scene().removeItem(self.parent.new_agent)
                self.parent.new_agent = None
                self.update()
                return

            all_del_objects = set()
            all_del_objects_old_brushes = []
            all_del_objects_old_pens = []
            del_input_ids = set()
            del_agents = set()
            for sel_item in self.parent.scene.selectedItems():
                all_del_objects.add(sel_item)
                if isinstance(sel_item, ConnectionLine):
                    # key of self.parent.lines where val = sel_item
                    for key, val in self.parent.lines.items():
                        if val == sel_item:
                            del_input_ids.add(key)
                            break
                elif isinstance(sel_item, DraggableAgent):
                    del_agents.add(sel_item.id)
                    # get all connected lines
                    for line_key in self.parent.lines.keys():
                        if line_key[0] == sel_item.id or line_key[1] == sel_item.id:
                            all_del_objects.add(self.parent.lines[line_key])
                            del_input_ids.add(line_key)

            if len(all_del_objects):
                # fill all objects with a red tint at 30% opacity, overlaying the current item image
                for item in all_del_objects:
                    old_brush = item.brush()
                    all_del_objects_old_brushes.append(old_brush)
                    # modify old brush and add a 30% opacity red fill
                    old_pixmap = old_brush.texture()
                    new_pixmap = old_pixmap.copy()  # create a copy of the old pixmap
                    painter = QPainter(new_pixmap)
                    painter.setCompositionMode(QPainter.CompositionMode_SourceAtop)
                    painter.fillRect(new_pixmap.rect(), QColor(255, 0, 0, 126))  # 76 out of 255 is about 30% opacity
                    painter.end()
                    new_brush = QBrush(new_pixmap)
                    item.setBrush(new_brush)

                    old_pen = item.pen()
                    all_del_objects_old_pens.append(old_pen)
                    new_pen = QPen(QColor(255, 0, 0, 255),
                                   old_pen.width())  # Create a new pen with 30% opacity red color
                    item.setPen(new_pen)

                self.parent.scene.update()

                # ask for confirmation
                retval = display_messagebox(
                    icon=QMessageBox.Warning,
                    text="Are you sure you want to delete the selected items?",
                    title="Delete Items",
                    buttons=QMessageBox.Ok | QMessageBox.Cancel
                )
                if retval == QMessageBox.Ok:
                    # delete all inputs from context
                    for member_id, inp_member_id in del_input_ids:
                        if inp_member_id == 0:  # todo - clean
                            sql.execute("""
                                DELETE FROM contexts_members_inputs 
                                WHERE member_id = ? 
                                    AND input_member_id IS NULL""",
                                        (member_id,))
                        else:
                            sql.execute("""
                                DELETE FROM contexts_members_inputs 
                                WHERE member_id = ? 
                                    AND input_member_id = ?""",
                                        (member_id, inp_member_id))
                    # delete all agents from context
                    for agent_id in del_agents:
                        sql.execute("""
                            UPDATE contexts_members 
                            SET del = 1
                            WHERE id = ?""", (agent_id,))

                    # load page chat
                    self.parent.parent.parent.load()
                else:
                    for item in all_del_objects:
                        item.setBrush(all_del_objects_old_brushes.pop(0))
                        item.setPen(all_del_objects_old_pens.pop(0))

        else:
            super(CustomGraphicsView, self).keyPressEvent(event)

    def mousePressEvent(self, event):
        if self.parent.new_agent:
            self.parent.add_member()
        else:
            mouse_scene_position = self.mapToScene(event.pos())
            for agent_id, agent in self.parent.members_in_view.items():
                if isinstance(agent, DraggableAgent):
                    if self.parent.new_line:
                        input_point_pos = agent.input_point.scenePos()
                        # if within 20px
                        if (mouse_scene_position - input_point_pos).manhattanLength() <= 20:
                            self.parent.new_line.attach_to_member(agent.id)
                            agent.close_btn.hide()
                    else:
                        output_point_pos = agent.output_point.scenePos()
                        output_point_pos.setX(output_point_pos.x() + 8)
                        # if within 20px
                        if (mouse_scene_position - output_point_pos).manhattanLength() <= 20:
                            self.parent.new_line = TemporaryConnectionLine(self.parent, agent)
                            self.parent.scene.addItem(self.parent.new_line)
                            return
            # check user bubble
            output_point_pos = self.parent.user_bubble.output_point.scenePos()
            output_point_pos.setX(output_point_pos.x() + 8)
            # if within 20px
            if (mouse_scene_position - output_point_pos).manhattanLength() <= 20:
                if self.parent.new_line:
                    self.parent.scene.removeItem(self.parent.new_line)

                self.parent.new_line = TemporaryConnectionLine(self.parent, self.parent.user_bubble)
                self.parent.scene.addItem(self.parent.new_line)
                return
            if self.parent.new_line:
                # Remove the temporary line from the scene and delete it
                self.scene().removeItem(self.parent.new_line)
                self.parent.new_line = None

        super(CustomGraphicsView, self).mousePressEvent(event)


class GroupTopBar(QWidget):
    def __init__(self, parent):
        super(GroupTopBar, self).__init__(parent)
        self.parent = parent

        self.layout = QHBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        #
        # self.btn_choose_member = QPushButton('Add Member', self)
        # self.btn_choose_member.clicked.connect(self.choose_member)
        # self.btn_choose_member.setFixedWidth(115)
        # self.layout.addWidget(self.btn_choose_member)
        self.btn_add_member = QPushButton(self)
        self.btn_add_member.setIcon(QIcon(QPixmap(":/resources/icon-new.png")))
        self.btn_add_member.setToolTip("Add a new member")
        self.btn_add_member.clicked.connect(self.choose_member)

        self.layout.addSpacing(11)
        self.layout.addWidget(self.btn_add_member)

        self.layout.addStretch(1)

        self.input_type_label = QLabel("Input type:", self)
        self.layout.addWidget(self.input_type_label)

        self.input_type_combo_box = QComboBox(self)
        self.input_type_combo_box.addItem("Message")
        self.input_type_combo_box.addItem("Context")
        self.input_type_combo_box.setFixedWidth(115)
        self.layout.addWidget(self.input_type_combo_box)

        self.input_type_combo_box.currentIndexChanged.connect(self.input_type_changed)

        self.input_type_combo_box.hide()
        self.input_type_label.hide()

        self.layout.addStretch(1)

        self.btn_clear = QPushButton('Clear', self)
        self.btn_clear.clicked.connect(self.clear_chat)
        self.btn_clear.setFixedWidth(75)
        self.layout.addWidget(self.btn_clear)

        self.dlg = None

    def choose_member(self):
        self.dlg = self.CustomQDialog(self)
        layout = QVBoxLayout(self.dlg)
        listWidget = self.CustomListWidget(self)
        layout.addWidget(listWidget)

        data = sql.get_results("""
            SELECT
                id,
                '' AS avatar,
                config,
                '' AS chat_button,
                '' AS del_button
            FROM agents
            ORDER BY id DESC""")
        for row_data in data:
            id, avatar, conf, chat_button, del_button = row_data
            conf = json.loads(conf)
            icon = QIcon(QPixmap(conf.get('general.avatar_path', '')))
            item = QListWidgetItem()
            item.setIcon(icon)

            name = conf.get('general.name', 'Assistant')
            item.setText(name)
            item.setData(Qt.UserRole, (id, conf))

            # set image
            listWidget.addItem(item)

        listWidget.itemDoubleClicked.connect(self.parent.insertAgent)

        self.dlg.exec_()

    class CustomQDialog(QDialog):  # todo - move these
        def __init__(self, parent=None):
            super().__init__(parent=parent)
            self.parent = parent

            self.setWindowTitle("Add Member")
            self.setWindowFlag(Qt.WindowMinimizeButtonHint, False)
            self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)

    class CustomListWidget(QListWidget):
        def __init__(self, parent=None):
            super().__init__(parent=parent)
            self.parent = parent

        def keyPressEvent(self, event):
            super().keyPressEvent(event)
            if event.key() != Qt.Key_Return:
                return
            item = self.currentItem()
            self.parent.insertAgent(item)

    def input_type_changed(self, index):
        sel_items = self.parent.scene.selectedItems()
        sel_lines = [item for item in sel_items if isinstance(item, ConnectionLine)]
        if len(sel_lines) != 1:
            return
        line = sel_lines[0]
        line_member_id, line_inp_member_id = line.key

        # 0 = message, 1 = context
        sql.execute("""
            UPDATE contexts_members_inputs
            SET type = ?
            WHERE member_id = ?
                AND COALESCE(input_member_id, 0) = ?""",
                    (index, line_member_id, line_inp_member_id))

        self.parent.load()

    def clear_chat(self):
        from agentpilot.context.base import Context
        retval = display_messagebox(
            icon=QMessageBox.Warning,
            text="Are you sure you want to permanently clear the chat messages? This should only be used when testing to preserve the context name. To keep your data start a new context.",
            title="Clear Chat",
            buttons=QMessageBox.Ok | QMessageBox.Cancel
        )

        if retval != QMessageBox.Ok:
            return

        sql.execute("""
            WITH RECURSIVE delete_contexts(id) AS (
                SELECT id FROM contexts WHERE id = ?
                UNION ALL
                SELECT contexts.id FROM contexts
                JOIN delete_contexts ON contexts.parent_id = delete_contexts.id
            )
            DELETE FROM contexts WHERE id IN delete_contexts AND id != ?;
        """, (self.parent.parent.parent.context.id, self.parent.parent.parent.context.id,))
        sql.execute("""
            WITH RECURSIVE delete_contexts(id) AS (
                SELECT id FROM contexts WHERE id = ?
                UNION ALL
                SELECT contexts.id FROM contexts
                JOIN delete_contexts ON contexts.parent_id = delete_contexts.id
            )
            DELETE FROM contexts_messages WHERE context_id IN delete_contexts;
        """, (self.parent.parent.parent.context.id,))
        sql.execute("""
        DELETE FROM contexts_messages WHERE context_id = ?""",
                    (self.parent.parent.parent.context.id,))

        page_chat = self.parent.parent.parent
        page_chat.context = Context(main=page_chat.main)
        self.parent.parent.parent.load()


class GroupSettings(QWidget):
    def __init__(self, parent):
        super(GroupSettings, self).__init__(parent)
        # self.context = self.parent.parent.context
        self.parent = parent
        self.main = parent.parent.main
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        self.group_topbar = GroupTopBar(self)
        layout.addWidget(self.group_topbar)

        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, 500, 200)
        self.scene.selectionChanged.connect(self.on_selection_changed)

        self.view = CustomGraphicsView(self.scene, self)

        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setFixedHeight(200)

        layout.addWidget(self.view)

        self.user_bubble = FixedUserBubble(self)
        self.scene.addItem(self.user_bubble)

        self.members_in_view = {}  # id: member
        self.lines = {}  # (member_id, inp_member_id): line

        self.new_line = None
        self.new_agent = None

        self.agent_settings = AgentSettings(self, is_context_member_agent=True)
        self.agent_settings.hide()
        layout.addWidget(self.agent_settings)
        layout.addStretch(1)

    def load(self):
        self.load_members()
        self.load_member_inputs()  # <-  agent settings is also loaded here

    def load_members(self):
        # Clear any existing members from the scene
        for m_id, member in self.members_in_view.items():
            member.close_btn.setParent(None)
            member.close_btn.deleteLater()

            member.hide_btn.setParent(None)
            member.hide_btn.deleteLater()

            self.scene.removeItem(member)

        self.members_in_view = {}

        query = """
            SELECT 
                cm.id,
                cm.agent_id,
                cm.agent_config,
                cm.loc_x,
                cm.loc_y,
                (SELECT GROUP_CONCAT(COALESCE(input_member_id, 0)) FROM contexts_members_inputs WHERE member_id = cm.id) as input_members,
                (SELECT GROUP_CONCAT(COALESCE(type, '')) FROM contexts_members_inputs WHERE member_id = cm.id) as input_member_types
            FROM contexts_members cm
            LEFT JOIN contexts_members_inputs cmi
                ON cmi.member_id = cm.id
            WHERE cm.context_id = ?
                AND cm.del = 0
            GROUP BY cm.id
        """
        members_data = sql.get_results(query, (self.parent.parent.context.id,))  # Pass the current context ID

        # Iterate over the fetched members and add them to the scene
        for id, agent_id, agent_config, loc_x, loc_y, member_inp_str, member_type_str in members_data:
            member = DraggableAgent(id, self, loc_x, loc_y, member_inp_str, member_type_str, agent_config)
            self.scene.addItem(member)
            self.members_in_view[id] = member

        # If there is only one member, hide the graphics view
        if len(self.members_in_view) == 1:
            self.select_ids([list(self.members_in_view.keys())[0]])
            self.view.hide()
        else:
            self.view.show()

    def load_member_inputs(self):
        for _, line in self.lines.items():
            self.scene.removeItem(line)
        self.lines = {}

        for m_id, member in self.members_in_view.items():
            for input_member_id, input_type in member.member_inputs.items():
                if input_member_id == 0:
                    input_member = self.user_bubble
                else:
                    input_member = self.members_in_view[input_member_id]
                key = (m_id, input_member_id)
                line = ConnectionLine(key, member.input_point, input_member.output_point, input_type)
                self.scene.addItem(line)
                self.lines[key] = line

    def select_ids(self, ids):
        for item in self.scene.selectedItems():
            item.setSelected(False)

        for _id in ids:
            self.members_in_view[_id].setSelected(True)

    def delete_ids(self, ids):
        self.select_ids(ids)
        self.view.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier))

    def insertAgent(self, item):
        self.group_topbar.dlg.close()

        self.view.show()
        mouse_scene_point = self.view.mapToScene(self.view.mapFromGlobal(QCursor.pos()))
        agent_id, agent_conf = item.data(Qt.UserRole)
        self.new_agent = TemporaryInsertableAgent(self, agent_id, agent_conf, mouse_scene_point)
        self.scene.addItem(self.new_agent)
        # focus the custom graphics view
        self.view.setFocus()

    def add_input(self, input_member_id, member_id):
        # insert self.new_agent into contexts_members table
        if member_id == input_member_id:
            return
        if input_member_id == 0:
            sql.execute("""
                INSERT INTO contexts_members_inputs
                    (member_id, input_member_id)
                SELECT ?, NULL
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM contexts_members_inputs
                    WHERE member_id = ? AND input_member_id IS NULL
                )""", (member_id, member_id))
        else:
            sql.execute("""
                INSERT INTO contexts_members_inputs
                    (member_id, input_member_id)
                SELECT ?, ?
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM contexts_members_inputs
                    WHERE member_id = ? AND input_member_id = ?
                )""", (member_id, input_member_id, member_id, input_member_id))
        self.scene.removeItem(self.new_line)
        self.new_line = None

        self.parent.parent.context.load()
        self.parent.parent.refresh()

    def add_member(self):
        sql.execute("""
            INSERT INTO contexts_members
                (context_id, agent_id, agent_config, loc_x, loc_y)
            SELECT
                ?, id, config, ?, ?
            FROM agents
            WHERE id = ?""", (self.parent.parent.context.id, self.new_agent.x(), self.new_agent.y(), self.new_agent.id))

        self.scene.removeItem(self.new_agent)
        self.new_agent = None

        self.parent.parent.load()

    def on_selection_changed(self):
        selected_agents = [x for x in self.scene.selectedItems() if isinstance(x, DraggableAgent)]
        selected_lines = [x for x in self.scene.selectedItems() if isinstance(x, ConnectionLine)]

        with block_signals(self.group_topbar):
            if len(selected_agents) == 1:
                self.agent_settings.show()
                self.load_agent_settings(selected_agents[0].id)
            else:
                self.agent_settings.hide()

            if len(selected_lines) == 1:
                self.group_topbar.input_type_label.show()
                self.group_topbar.input_type_combo_box.show()
                line = selected_lines[0]
                self.group_topbar.input_type_combo_box.setCurrentIndex(line.input_type)
            else:
                self.group_topbar.input_type_label.hide()
                self.group_topbar.input_type_combo_box.hide()

    def load_agent_settings(self, agent_id):
        agent_config_json = sql.get_scalar('SELECT agent_config FROM contexts_members WHERE id = ?', (agent_id,))

        self.agent_settings.agent_id = agent_id
        self.agent_settings.agent_config = json.loads(agent_config_json) if agent_config_json else {}
        self.agent_settings.load()


# class PythonHighlighter(QSyntaxHighlighter):
#     KEYWORDS = [
#         "and", "as", "assert", "break", "class", "continue", "def", "del",
#         "elif", "else", "except", "exec", "finally", "for", "from", "global",
#         "if", "import", "in", "is", "lambda", "not", "or", "pass", "print",
#         "raise", "return", "try", "while", "with", "yield"
#     ]
#
#     OPERATORS = [
#         '=', '==', '!=', '<', '<=', '>', '>=', '\+', '-', '\*', '/', '//',
#         '\%', '\*\*', '\+=', '-=', '\*=', '/=', '\%=', '\^', '\|', '\&',
#         '\~', '>>', '<<'
#     ]
#
#     BRACKETS = [
#         '\{', '\}', '\(', '\)', '\[', '\]'
#     ]
#
#     def __init__(self, document):
#         super(PythonHighlighter, self).__init__(document)
#
#         self.highlightingRules = []
#
#         # Keyword, operator, and bracket rules
#         keywordFormat = QTextCharFormat()
#         keywordFormat.setForeground(QColor("#bf6237"))
#         keywordFormat.setFontWeight(QFont.Bold)
#         for word in PythonHighlighter.KEYWORDS:
#             pattern = r'\b{}\b'.format(word)
#             regex = QRegularExpression(pattern)
#             rule = {'pattern': regex, 'format': keywordFormat}
#             self.highlightingRules.append(rule)
#
#         operatorFormat = QTextCharFormat()
#         operatorFormat.setForeground(QColor("red"))
#         for op in PythonHighlighter.OPERATORS:
#             pattern = r'{}'.format(op)
#             regex = QRegularExpression(pattern)
#             rule = {'pattern': regex, 'format': operatorFormat}
#             self.highlightingRules.append(rule)
#
#         bracketFormat = QTextCharFormat()
#         bracketFormat.setForeground(QColor("darkGreen"))
#         for bracket in PythonHighlighter.BRACKETS:
#             pattern = r'{}'.format(bracket)
#             regex = QRegularExpression(pattern)
#             rule = {'pattern': regex, 'format': bracketFormat}
#             self.highlightingRules.append(rule)
#
#         # Multi-line strings (quotes)
#         self.multiLineCommentFormat = QTextCharFormat()
#         self.multiLineCommentFormat.setForeground(QColor("grey"))
#         self.commentStartExpression = QRegularExpression(r"'''|\"\"\"")
#         self.commentEndExpression = QRegularExpression(r"'''|\"\"\"")
#
#     # def set_text_to_highlight(self, text):
#     #     self.text_to_highlight = text
#     #
#     #     # This method is automatically called by the QSyntaxHighlighter base class.
#     #     # We override it to implement our custom syntax highlighting.
#     def highlightBlock(self, text):
#         # Single-line highlighting
#         for rule in self.highlightingRules:
#             expression = QRegularExpression(rule['pattern'])
#             it = expression.globalMatch(text)
#             while it.hasNext():
#                 match = it.next()
#                 self.setFormat(match.capturedStart(), match.capturedLength(), rule['format'])
#
#         # Multi-line highlighting (multi-line strings)
#         self.setCurrentBlockState(0)
#
#         startIndex = 0
#         if self.previousBlockState() != 1:
#             match = self.commentStartExpression.match(text)
#             startIndex = match.capturedStart()
#
#         while startIndex >= 0:
#             match = self.commentEndExpression.match(text, startIndex)
#             endIndex = match.capturedStart()
#             commentLength = 0
#             if endIndex == -1:
#                 self.setCurrentBlockState(1)
#                 commentLength = len(text) - startIndex
#             else:
#                 commentLength = endIndex - startIndex + match.capturedLength()
#             self.setFormat(startIndex, commentLength, self.multiLineCommentFormat)
#             startIndex = self.commentStartExpression.match(text, startIndex + commentLength).capturedStart()
#
#     # def highlightBlock(self, text):
#     #     # Check for a code block
#     #     if self.currentBlockState() == 1:
#     #         self.setFormat(0, len(text), self.codeBlockFormat)
#     #         end_index = self.codeBlockEndExpression.search(text)
#     #         if end_index is None:
#     #             self.setCurrentBlockState(1)
#     #         else:
#     #             self.setCurrentBlockState(0)
#     #
#     #     for pattern, format in self.highlightingRules:
#     #         match_iterator = pattern.finditer(text)
#     #         for match in match_iterator:
#     #             start, end = match.span()
#     #             self.setFormat(start, end - start, format)
#     #
#     #     # Check if we're entering a code block
#     #     start_index = self.codeBlockStartExpression.search(text)
#     #     if start_index is not None:
#     #         self.setCurrentBlockState(1)
#
# #     # def highlightBlock(self, text):
# #     #     # If it's a code block line
# #     #     text = self.text_to_highlight
# #     #     if self.currentBlockState() == 1:
# #     #         self.setFormat(0, len(text), self.codeBlockFormat)
# #     #         end_index = self.codeBlockEndExpression.search(text)
# #     #         if end_index is None:
# #     #             # This block continues to the next block
# #     #             self.setCurrentBlockState(1)
# #     #         else:
# #     #             self.setCurrentBlockState(0)
# #     #             for pattern, format in self.highlightingRules:
# #     #                 match = pattern.search(text)
# #     #                 while match is not None:
# #     #                     start, end = match.span()
# #     #                     self.setFormat(start, end - start, format)
# #     #                     match = pattern.search(text, end)
# #     #     else:  # Not in a code block
# #     #         start_index = self.codeBlockStartExpression.search(text)
# #     #         if start_index is not None:
# #     #             self.setCurrentBlockState(1)


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
        # self.page_models = self.Page_Model_Settings(self)
        self.content.addWidget(self.page_system)
        self.content.addWidget(self.page_api)
        self.content.addWidget(self.page_display)
        self.content.addWidget(self.page_block)
        # self.content.addWidget(self.page_models)

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
        self.content.currentWidget().load()

    def update_config(self, key, value):
        config.set_value(key, value)
        config.load_config()
        exclude_load = [
            'system.auto_title_prompt',
        ]
        if key in exclude_load:
            return
        self.main.set_stylesheet()
        self.main.page_chat.load()

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
            self.btn_sandboxes = self.Settings_SideBar_Button(main=main, text='Sandbox')
            self.btn_sandboxes.setFont(font)

            self.layout = QVBoxLayout(self)
            self.layout.setSpacing(0)
            self.layout.setContentsMargins(0, 0, 0, 0)

            # Create a button group and add buttons to it
            self.button_group = QButtonGroup(self)
            self.button_group.addButton(self.btn_system, 0)  # 0 is the ID associated with the button
            self.button_group.addButton(self.btn_api, 1)
            self.button_group.addButton(self.btn_display, 2)
            self.button_group.addButton(self.btn_blocks, 3)
            self.button_group.addButton(self.btn_sandboxes, 4)

            # Connect button toggled signal
            self.button_group.buttonToggled[QAbstractButton, bool].connect(self.onButtonToggled)

            self.layout.addWidget(self.btn_system)
            self.layout.addWidget(self.btn_api)
            self.layout.addWidget(self.btn_display)
            self.layout.addWidget(self.btn_blocks)
            self.layout.addWidget(self.btn_sandboxes)

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
                super().__init__(parent=main)
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

            # text field for dbpath
            self.dev_mode = QCheckBox()
            self.form_layout.addRow(QLabel('Dev Mode:'), self.dev_mode)
            self.dev_mode.stateChanged.connect(lambda state: self.toggle_dev_mode(state))

            self.model_combo = ModelComboBox()
            self.model_combo.setFixedWidth(150)
            self.form_layout.addRow(QLabel('Auto-title Model:'), self.model_combo)
            # connect model data key to update config
            self.model_combo.currentTextChanged.connect(
                lambda: self.parent.update_config('system.auto_title_model', self.model_combo.currentData()))

            # self.model_combo.currentTextChanged.connect(
            #     lambda model: self.parent.update_config('system.auto_title_model',

            self.model_prompt = QTextEdit()
            self.model_prompt.setFixedHeight(45)
            self.form_layout.addRow(QLabel('Auto-title Prompt:'), self.model_prompt)
            self.model_prompt.textChanged.connect(
                lambda: self.parent.update_config('system.auto_title_prompt', self.model_prompt.toPlainText()))

            self.form_layout.addRow(QLabel(''), QLabel(''))

            # add a button 'Reset database'
            self.reset_app_btn = QPushButton('Reset Application')
            self.reset_app_btn.clicked.connect(self.reset_application)
            self.form_layout.addRow(self.reset_app_btn, QLabel(''))

            # add button 'Fix empty titles'
            self.fix_empty_titles_btn = QPushButton('Fix Empty Titles')
            self.fix_empty_titles_btn.clicked.connect(self.fix_empty_titles)
            self.form_layout.addRow(self.fix_empty_titles_btn, QLabel(''))

            self.setLayout(self.form_layout)

        def load(self):
            # config = self.parent.main.page_chat.agent.config
            with block_signals(self):
                self.dev_mode.setChecked(config.get_value('system.dev_mode', False))
                model_name = config.get_value('system.auto_title_model', '')
                index = self.model_combo.findData(model_name)
                self.model_combo.setCurrentIndex(index)
                self.model_prompt.setText(config.get_value('system.auto_title_prompt', ''))

        def toggle_dev_mode(self, state):
            self.parent.update_config('system.dev_mode', state)
            self.refresh_dev_mode()

        def refresh_dev_mode(self):
            state = config.get_value('system.dev_mode', False)
            main = self.parent.main
            main.page_chat.topbar.btn_info.setVisible(state)
            main.page_chat.topbar.group_settings.group_topbar.btn_clear.setVisible(state)
            main.page_settings.page_system.reset_app_btn.setVisible(state)
            main.page_settings.page_system.fix_empty_titles_btn.setVisible(state)

        def reset_application(self):
            from agentpilot.context.base import Context

            retval = display_messagebox(
                icon=QMessageBox.Warning,
                text="Are you sure you want to permanently reset the database and config? This will permanently delete all contexts, messages, and logs.",
                title="Reset Database",
                buttons=QMessageBox.Ok | QMessageBox.Cancel
            )

            if retval != QMessageBox.Ok:
                return

            sql.execute('DELETE FROM contexts_messages')
            sql.execute('DELETE FROM contexts_members')
            sql.execute('DELETE FROM contexts')
            sql.execute('DELETE FROM embeddings WHERE id > 1984')
            sql.execute('DELETE FROM logs')
            sql.execute('VACUUM')
            self.parent.update_config('system.dev_mode', False)
            self.refresh_dev_mode()
            self.parent.main.page_chat.context = Context(main=self.parent.main)
            self.load()

        def fix_empty_titles(self):
            retval = display_messagebox(
                icon=QMessageBox.Warning,
                text="Are you sure you want to fix empty titles? This could be very expensive and may take a while. The application will be unresponsive until it is finished.",
                title="Fix titles",
                buttons=QMessageBox.Yes | QMessageBox.No
            )

            if retval != QMessageBox.Yes:
                return

            # get all contexts with empty titles
            contexts_first_msgs = sql.get_results("""
                SELECT c.id, cm.msg
                FROM contexts c
                INNER JOIN (
                    SELECT *
                    FROM contexts_messages
                    WHERE rowid IN (
                        SELECT MIN(rowid)
                        FROM contexts_messages
                        GROUP BY context_id
                    )
                ) cm ON c.id = cm.context_id
                WHERE c.summary = '';
            """, return_type='dict')

            model_name = config.get_value('system.auto_title_model', 'gpt-3.5-turbo')
            model_obj = (model_name, self.parent.main.system.models.to_dict()[model_name])  # todo make prettier

            prompt = config.get_value('system.auto_title_prompt',
                                      'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}')
            try:
                for context_id, msg in contexts_first_msgs.items():
                    context_prompt = prompt.format(user_msg=msg)

                    title = llm.get_scalar(context_prompt, model_obj=model_obj)
                    title = title.replace('\n', ' ').strip("'").strip('"')
                    sql.execute('UPDATE contexts SET summary = ? WHERE id = ?', (title, context_id))

            except Exception as e:
                # show error message
                display_messagebox(
                    icon=QMessageBox.Warning,
                    text="Error generating titles: " + str(e),
                    title="Error",
                    buttons=QMessageBox.Ok
                )

    class Page_Display_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.form_layout = QFormLayout()

            # Primary Color
            primary_color_label = QLabel('Primary Color:')
            primary_color_label.setFixedWidth(220)  # Stops width changing when changing role
            self.primary_color_picker = ColorPickerButton()
            self.form_layout.addRow(primary_color_label, self.primary_color_picker)
            self.primary_color_picker.colorChanged.connect(
                lambda color: self.parent.update_config('display.primary_color', color))

            # Secondary Color
            self.secondary_color_picker = ColorPickerButton()
            self.form_layout.addRow(QLabel('Secondary Color:'), self.secondary_color_picker)
            self.secondary_color_picker.colorChanged.connect(
                lambda color: self.parent.update_config('display.secondary_color', color))

            # Text Color
            self.text_color_picker = ColorPickerButton()
            self.form_layout.addRow(QLabel('Text Color:'), self.text_color_picker)
            self.text_color_picker.colorChanged.connect(
                lambda color: self.parent.update_config('display.text_color', color))

            # Text Font (dummy data)
            self.text_font_dropdown = CComboBox()
            font_database = QFontDatabase()
            available_fonts = font_database.families()
            self.text_font_dropdown.addItems(available_fonts)

            font_delegate = self.FontItemDelegate(self.text_font_dropdown)
            self.text_font_dropdown.setItemDelegate(font_delegate)
            self.form_layout.addRow(QLabel('Text Font:'), self.text_font_dropdown)
            self.text_font_dropdown.currentTextChanged.connect(
                lambda font: self.parent.update_config('display.text_font', font))

            # Text Size
            self.text_size_input = QSpinBox()
            self.text_size_input.setFixedWidth(150)
            self.text_size_input.setRange(6, 72)  # Assuming a reasonable range for font sizes
            self.form_layout.addRow(QLabel('Text Size:'), self.text_size_input)
            self.text_size_input.valueChanged.connect(lambda size: self.parent.update_config('display.text_size', size))

            # Show Agent Bubble Avatar (combobox with In Group/Always/Never)
            self.agent_avatar_dropdown = CComboBox()
            self.agent_avatar_dropdown.addItems(['In Group', 'Always', 'Never'])
            self.form_layout.addRow(QLabel('Show Agent Bubble Avatar:'), self.agent_avatar_dropdown)
            self.agent_avatar_dropdown.currentTextChanged.connect(
                lambda text: self.parent.update_config('display.agent_avatar_show', text))

            # Agent Bubble Avatar position Top or Middle
            self.agent_avatar_position_dropdown = CComboBox()
            self.agent_avatar_position_dropdown.addItems(['Top', 'Middle'])
            self.form_layout.addRow(QLabel('Agent Bubble Avatar Position:'), self.agent_avatar_position_dropdown)
            self.agent_avatar_position_dropdown.currentTextChanged.connect(
                lambda text: self.parent.update_config('display.agent_avatar_position', text))
            # add spacer
            self.form_layout.addRow(QLabel(''), QLabel(''))

            # Role Combo Box
            self.role_dropdown = RoleComboBox()
            # self.form_layout.addRow(QLabel('Role:'), self.role_dropdown)
            self.form_layout.addRow(self.role_dropdown)
            self.role_dropdown.currentIndexChanged.connect(self.load_role_config)

            selected_role = self.role_dropdown.currentText().title()
            # Bubble Colors
            self.bubble_bg_color_picker = ColorPickerButton()
            self.bubble_bg_color_label = QLabel(f'{selected_role} Bubble Background Color:')
            self.form_layout.addRow(self.bubble_bg_color_label, self.bubble_bg_color_picker)
            self.bubble_bg_color_picker.colorChanged.connect(self.role_config_changed)

            self.bubble_text_color_picker = ColorPickerButton()
            self.bubble_text_color_label = QLabel(f'{selected_role} Bubble Text Color:')
            self.form_layout.addRow(self.bubble_text_color_label, self.bubble_text_color_picker)
            self.bubble_text_color_picker.colorChanged.connect(self.role_config_changed)

            self.bubble_image_size_input = QLineEdit()
            self.bubble_image_size_label = QLabel(f'{selected_role} Image Size:')
            self.bubble_image_size_input.setValidator(QIntValidator(3, 100))
            self.form_layout.addRow(self.bubble_image_size_label, self.bubble_image_size_input)
            self.bubble_image_size_input.textChanged.connect(self.role_config_changed)

            self.setLayout(self.form_layout)

        def load_role_config(self):
            with block_signals(self):
                role_id = self.role_dropdown.currentData()
                role_config_str = sql.get_scalar("""SELECT `config` FROM roles WHERE id = ? """, (role_id,))
                role_config = json.loads(role_config_str)
                bg = role_config.get('display.bubble_bg_color', '#ffffff')
                self.bubble_bg_color_picker.set_color(bg)
                self.bubble_text_color_picker.set_color(role_config.get('display.bubble_text_color', '#ffffff'))
                self.bubble_image_size_input.setText(str(role_config.get('display.bubble_image_size', 50)))

                role = self.role_dropdown.currentText().title()
                self.bubble_bg_color_label.setText(f'{role} Bubble Background Color:')
                self.bubble_text_color_label.setText(f'{role} Bubble Text Color:')
                self.bubble_image_size_label.setText(f'{role} Image Size:')

        def role_config_changed(self):
            role_id = self.role_dropdown.currentData()
            role_config_str = sql.get_scalar("""SELECT `config` FROM roles WHERE id = ? """, (role_id,))
            role_config = json.loads(role_config_str)
            role_config['display.bubble_bg_color'] = self.bubble_bg_color_picker.get_color()
            role_config['display.bubble_text_color'] = self.bubble_text_color_picker.get_color()
            role_config['display.bubble_image_size'] = self.bubble_image_size_input.text()
            sql.execute("""UPDATE roles SET `config` = ? WHERE id = ? """, (json.dumps(role_config), role_id,))
            self.parent.main.system.roles.load()

        def load(self):
            with block_signals(self):
                self.primary_color_picker.set_color(config.get_value('display.primary_color'))
                self.secondary_color_picker.set_color(config.get_value('display.secondary_color'))
                self.text_color_picker.set_color(config.get_value('display.text_color'))
                self.text_font_dropdown.setCurrentText(config.get_value('display.text_font'))
                self.text_size_input.setValue(config.get_value('display.text_size'))
                self.agent_avatar_dropdown.setCurrentText(config.get_value('display.agent_avatar_show'))
                self.agent_avatar_position_dropdown.setCurrentText(config.get_value('display.agent_avatar_position'))

            self.load_role_config()

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

    class Page_API_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent

            self.layout = QVBoxLayout(self)

            # container for the table and a 20px wide sidebar
            self.table_layout = QHBoxLayout()
            self.table_layout.setContentsMargins(0, 0, 0, 0)
            self.table_layout.setSpacing(0)

            self.table_container = QWidget(self)
            self.table_container.setLayout(self.table_layout)

            # API settings part
            self.table = BaseTableWidget(self)
            self.table.setColumnCount(4)
            self.table.setColumnHidden(0, True)
            self.table.setHorizontalHeaderLabels(['ID', 'Name', 'Client Key', 'Private Key'])
            self.table.horizontalHeader().setStretchLastSection(True)
            self.table.itemChanged.connect(self.item_edited)
            self.table.currentItemChanged.connect(self.load_models)

            self.table_layout.addWidget(self.table)

            self.button_layout = QVBoxLayout()
            self.button_layout.addStretch(1)
            self.new_api_button = self.Button_New_API(self)
            self.button_layout.addWidget(self.new_api_button)
            self.del_api_button = self.Button_Delete_API(self)
            self.button_layout.addWidget(self.del_api_button)

            self.table_layout.addLayout(self.button_layout)

            self.layout.addWidget(self.table_container)

            # Tab Widget
            self.tab_widget = QTabWidget(self)

            # Models Tab
            self.models_tab = QWidget(self.tab_widget)
            self.models_layout = QHBoxLayout(self.models_tab)

            # Create a container for the model list and a button bar above
            self.models_container = QWidget(self.models_tab)
            self.models_container_layout = QVBoxLayout(self.models_container)
            self.models_container_layout.setContentsMargins(0, 0, 0, 0)
            self.models_container_layout.setSpacing(0)

            self.models_button_layout = QHBoxLayout()
            self.models_button_layout.addStretch(1)
            self.new_model_button = self.Button_New_Model(self)
            self.models_button_layout.addWidget(self.new_model_button)
            self.del_model_button = self.Button_Delete_Model(self)
            self.models_button_layout.addWidget(self.del_model_button)
            self.models_container_layout.addLayout(self.models_button_layout)

            self.models_list = QListWidget(self.models_container)
            self.models_list.setSelectionMode(QListWidget.SingleSelection)
            self.models_list.setFixedWidth(200)
            self.models_container_layout.addWidget(self.models_list)
            self.models_layout.addWidget(self.models_container)

            # # self.models_label = QLabel("Models:")
            # self.models_list = QListWidget(self.models_tab)
            # self.models_list.setSelectionMode(QListWidget.SingleSelection)
            # self.models_list.setFixedWidth(200)
            # # self.models_layout.addWidget(self.models_label)
            # self.models_layout.addWidget(self.models_list)

            self.fields_layout = QVBoxLayout()

            # connect model list selection changed to load_model_fields
            self.models_list.currentItemChanged.connect(self.load_model_fields)

            self.alias_label = QLabel("Alias")
            self.alias_label.setStyleSheet("QLabel { color : #7d7d7d; }")
            self.alias_label.hide()
            self.alias_field = QLineEdit()
            self.alias_field.hide()
            alias_layout = QHBoxLayout()
            alias_layout.addWidget(self.alias_label)
            alias_layout.addWidget(self.alias_field)
            self.fields_layout.addLayout(alias_layout)

            self.model_name_label = QLabel("Model name")
            self.model_name_label.setStyleSheet("QLabel { color : #7d7d7d; }")
            self.model_name_label.hide()
            self.model_name_field = QLineEdit()
            self.model_name_field.hide()
            model_name_layout = QHBoxLayout()
            model_name_layout.addWidget(self.model_name_label)
            model_name_layout.addWidget(self.model_name_field)
            self.fields_layout.addLayout(model_name_layout)

            self.api_base_label = QLabel("Api Base")
            self.api_base_label.setStyleSheet("QLabel { color : #7d7d7d; }")
            self.api_base_label.hide()
            self.api_base_field = QLineEdit()
            self.api_base_field.hide()
            api_base_layout = QHBoxLayout()
            api_base_layout.addWidget(self.api_base_label)
            api_base_layout.addWidget(self.api_base_field)
            self.fields_layout.addLayout(api_base_layout)

            self.custom_provider_label = QLabel("Custom provider")
            self.custom_provider_label.setStyleSheet("QLabel { color : #7d7d7d; }")
            self.custom_provider_label.hide()
            self.custom_provider_field = QLineEdit()
            self.custom_provider_field.hide()
            custom_provider_layout = QHBoxLayout()
            custom_provider_layout.addWidget(self.custom_provider_label)
            custom_provider_layout.addWidget(self.custom_provider_field)
            self.fields_layout.addLayout(custom_provider_layout)

            self.temperature_label = QLabel("Temperature")
            self.temperature_label.setStyleSheet("QLabel { color : #7d7d7d; }")
            self.temperature_label.hide()
            self.temperature_field = QLineEdit()
            self.temperature_field.hide()
            # self.temperature_field.setValidator(QValidator(3, 100))
            # float validator
            self.temperature_field.setValidator(QDoubleValidator(0.0, 100.0, 2))
            temperature_layout = QHBoxLayout()
            temperature_layout.addWidget(self.temperature_label)
            temperature_layout.addWidget(self.temperature_field)
            self.fields_layout.addLayout(temperature_layout)

            self.models_layout.addLayout(self.fields_layout)

            # Voices Taboo
            self.voices_tab = QWidget(self.tab_widget)
            self.voices_layout = QVBoxLayout(self.voices_tab)
            # self.voices_label = QLabel("Voices:")
            self.voices_list = QListWidget(self.voices_tab)
            self.voices_list.setSelectionMode(QListWidget.SingleSelection)
            self.voices_list.setFixedWidth(200)
            # self.voices_layout.addWidget(self.voices_label)
            self.voices_layout.addWidget(self.voices_list)

            # Add tabs to the Tab Widget
            self.tab_widget.addTab(self.models_tab, "Models")
            self.tab_widget.addTab(self.voices_tab, "Voices")

            # Add Tab Widget to the main layout
            self.layout.addWidget(self.tab_widget)
            self.layout.addStretch(1)

            # connect signals for each field change

            self.alias_field.textChanged.connect(self.update_model_config)
            self.model_name_field.textChanged.connect(self.update_model_config)
            self.api_base_field.textChanged.connect(self.update_model_config)
            self.custom_provider_field.textChanged.connect(self.update_model_config)
            self.temperature_field.textChanged.connect(self.update_model_config)

        def load(self):
            self.load_api_table()
            self.load_models()

        def load_api_table(self):
            with block_signals(self):
                # self.table.blockSignals(True)
                self.table.setRowCount(0)
                data = sql.get_results("""
                    SELECT
                        id,
                        name,
                        client_key,
                        priv_key
                    FROM apis""")
                for row_data in data:
                    row_position = self.table.rowCount()
                    self.table.insertRow(row_position)
                    for column, item in enumerate(row_data):
                        self.table.setItem(row_position, column, QTableWidgetItem(str(item)))
            # self.table.blockSignals(False)

        def load_models(self):
            # Clear the current items in the list
            self.models_list.clear()

            # if none selected then return
            if self.table.currentRow() == -1:
                return

            # Get the currently selected API's ID
            current_api_id = self.table.item(self.table.currentRow(), 0).text()

            # Fetch the models from the database
            data = sql.get_results("""
                SELECT 
                    id, 
                    alias 
                FROM models 
                WHERE api_id = ?
                ORDER BY alias""", (current_api_id,))
            for row_data in data:
                model_id, model_name = row_data
                item = QListWidgetItem(model_name)
                item.setData(Qt.UserRole, model_id)
                self.models_list.addItem(item)

            show_fields = (self.models_list.count() > 0)  # and (self.models_list.currentItem() is not None)
            self.alias_label.setVisible(show_fields)
            self.alias_field.setVisible(show_fields)
            self.model_name_label.setVisible(show_fields)
            self.model_name_field.setVisible(show_fields)
            self.api_base_label.setVisible(show_fields)
            self.api_base_field.setVisible(show_fields)
            self.custom_provider_label.setVisible(show_fields)
            self.custom_provider_field.setVisible(show_fields)
            self.temperature_label.setVisible(show_fields)
            self.temperature_field.setVisible(show_fields)

            # Select the first model in the list by default
            if self.models_list.count() > 0:
                self.models_list.setCurrentRow(0)

        def load_model_fields(self):
            current_item = self.models_list.currentItem()
            if current_item is None:
                return
            current_selected_id = self.models_list.currentItem().data(Qt.UserRole)

            model_data = sql.get_results("""
                SELECT
                    alias,
                    model_name,
                    model_config
                FROM models
                WHERE id = ?""",
                 (current_selected_id,),
                 return_type='hdict')
            if len(model_data) == 0:
                return
            alias = model_data['alias']
            model_name = model_data['model_name']
            model_config = json.loads(model_data['model_config'])
            api_base = model_config.get('api_base', '')
            custom_provider = model_config.get('custom_llm_provider', '')
            temperature = model_config.get('temperature', '')

            with block_signals(self):
                self.alias_field.setText(alias)
                self.model_name_field.setText(model_name)
                self.api_base_field.setText(api_base)
                self.custom_provider_field.setText(custom_provider)
                self.temperature_field.setText(str(temperature))

        def get_model_config(self):
            # Retrieve the current values from the widgets and construct a new 'config' dictionary
            # temp = int(self.temperature_field.text()) if self.temperature_field.text() != '' else None
            current_config = {
                'api_base': self.api_base_field.text(),
                'custom_llm_provider': self.custom_provider_field.text(),
                'temperature': self.temperature_field.text()
            }
            return json.dumps(current_config)

        def update_model_config(self):
            current_model = self.models_list.currentItem()
            if current_model is None:
                return

            current_model_id = current_model.data(Qt.UserRole)
            current_config = self.get_model_config()
            sql.execute("UPDATE models SET model_config = ? WHERE id = ?", (current_config, current_model_id))

            model_alias = self.alias_field.text()
            model_name = self.model_name_field.text()
            sql.execute("UPDATE models SET alias = ?, model_name = ? WHERE id = ?",
                        (model_alias, model_name, current_model_id))
            # self.load()

        class Button_New_API(QPushButton):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent
                self.clicked.connect(self.new_api)
                self.icon = QIcon(QPixmap(":/resources/icon-new.png"))  # Path to your icon
                self.setIcon(self.icon)
                self.setFixedSize(25, 25)
                self.setIconSize(QSize(18, 18))

            def new_api(self):
                pass
                # global PIN_STATE
                # current_pin_state = PIN_STATE
                # PIN_STATE = True
                # text, ok = QInputDialog.getText(self, 'New Model', 'Enter a name for the model:')
                #
                # # Check if the OK button was clicked
                # if ok and text:
                #     current_api_id = self.parent.table.item(self.parent.table.currentRow(), 0).text()
                #     sql.execute("INSERT INTO `models` (`alias`, `api_id`, `model_name`) VALUES (?, ?, '')", (text, current_api_id,))
                #     self.parent.load_models()
                # PIN_STATE = current_pin_state

        class Button_Delete_API(QPushButton):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent
                self.clicked.connect(self.delete_api)
                self.icon = QIcon(QPixmap(":/resources/icon-minus.png"))
                self.setIcon(self.icon)
                self.setFixedSize(25, 25)
                self.setIconSize(QSize(18, 18))

            def delete_api(self):
                pass
                # global PIN_STATE
                #
                # current_item = self.parent.models_list.currentItem()
                # if current_item is None:
                #     return
                #
                # msg = QMessageBox()
                # msg.setIcon(QMessageBox.Warning)
                # msg.setText(f"Are you sure you want to delete this model?")
                # msg.setWindowTitle("Delete Model")
                # msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                #
                # current_pin_state = PIN_STATE
                # PIN_STATE = True
                # retval = msg.exec_()
                # PIN_STATE = current_pin_state
                # if retval != QMessageBox.Yes:
                #     return
                #
                # # Logic for deleting a model from the database
                # current_model_id = current_item.data(Qt.UserRole)
                # sql.execute("DELETE FROM `models` WHERE `id` = ?", (current_model_id,))
                # self.parent.load_models()  # Reload the list of models

        class Button_New_Model(QPushButton):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent
                self.clicked.connect(self.new_model)
                self.icon = QIcon(QPixmap(":/resources/icon-new.png"))  # Path to your icon
                self.setIcon(self.icon)
                self.setFixedSize(25, 25)
                self.setIconSize(QSize(18, 18))

            def new_model(self):
                global PIN_STATE
                current_pin_state = PIN_STATE
                PIN_STATE = True
                text, ok = QInputDialog.getText(self, 'New Model', 'Enter a name for the model:')

                # Check if the OK button was clicked
                if ok and text:
                    current_api_id = self.parent.table.item(self.parent.table.currentRow(), 0).text()
                    sql.execute("INSERT INTO `models` (`alias`, `api_id`, `model_name`) VALUES (?, ?, '')",
                                (text, current_api_id,))
                    self.parent.load_models()
                    self.parent.parent.main.page_chat.load()

                PIN_STATE = current_pin_state

        class Button_Delete_Model(QPushButton):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent
                self.clicked.connect(self.delete_model)
                self.icon = QIcon(QPixmap(":/resources/icon-minus.png"))
                self.setIcon(self.icon)
                self.setFixedSize(25, 25)
                self.setIconSize(QSize(18, 18))

            def delete_model(self):
                global PIN_STATE

                current_item = self.parent.models_list.currentItem()
                if current_item is None:
                    return

                retval = display_messagebox(
                    icon=QMessageBox.Warning,
                    text="Are you sure you want to delete this model?",
                    title="Delete Model",
                    buttons=QMessageBox.Yes | QMessageBox.No
                )

                # current_pin_state = PIN_STATE
                # PIN_STATE = True
                # retval = msg.exec_()
                # PIN_STATE = current_pin_state

                if retval != QMessageBox.Yes:
                    return

                # Logic for deleting a model from the database
                current_model_id = current_item.data(Qt.UserRole)
                sql.execute("DELETE FROM `models` WHERE `id` = ?", (current_model_id,))
                self.parent.load_models()  # Reload the list of models
                self.parent.parent.main.page_chat.context.load()
                self.parent.parent.main.page_chat.refresh()

        def item_edited(self, item):
            row = item.row()
            api_id = self.table.item(row, 0).text()

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

            api.load_api_keys()

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

            # container holding a button bar and the table
            self.table_container = QWidget(self)
            self.table_container_layout = QVBoxLayout(self.table_container)
            self.table_container_layout.setContentsMargins(0, 0, 0, 0)
            self.table_container_layout.setSpacing(0)

            # button bar
            self.button_layout = QHBoxLayout()
            self.add_block_button = QPushButton(self)
            self.add_block_button.setIcon(QIcon(QPixmap(":/resources/icon-new.png")))
            self.add_block_button.clicked.connect(self.add_block)
            self.button_layout.addWidget(self.add_block_button)

            self.delete_block_button = QPushButton(self)
            self.delete_block_button.setIcon(QIcon(QPixmap(":/resources/icon-minus.png")))
            self.delete_block_button.clicked.connect(self.delete_block)
            self.button_layout.addWidget(self.delete_block_button)
            self.button_layout.addStretch(1)

            # add the button bar to the table container layout
            self.table_container_layout.addLayout(self.button_layout)
            # add the table to the table container layout
            self.table_container_layout.addWidget(self.table)
            # Adding table container to the layout
            self.layout.addWidget(self.table_container)

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
            with block_signals(self):
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
            self.parent.main.system.blocks.load()

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

            self.parent.main.system.blocks.load()

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

            with block_signals(self):
                self.block_data_text_area.setText(att_text)

        def add_block(self):
            text, ok = QInputDialog.getText(self, 'New Block', 'Enter the placeholder tag for the block:')

            if ok:
                sql.execute("INSERT INTO `blocks` (`name`, `text`) VALUES (?, '')", (text,))
                self.load()
                self.parent.main.system.blocks.load()

        def delete_block(self):
            current_row = self.table.currentRow()
            if current_row == -1: return
            # ask confirmation qdialog
            retval = display_messagebox(
                icon=QMessageBox.Warning,
                text="Are you sure you want to delete this block?",
                title="Delete Block",
                buttons=QMessageBox.Yes | QMessageBox.No
            )
            if retval != QMessageBox.Yes:
                return

            block_id = self.table.item(current_row, 0).text()
            sql.execute("DELETE FROM `blocks` WHERE `id` = ?", (block_id,))
            self.load()
            self.parent.main.system.blocks.load()


class AgentSettings(QWidget):
    def __init__(self, parent, is_context_member_agent=False):
        super().__init__(parent=parent)
        self.parent = parent
        self.main = parent.main
        self.is_context_member_agent = is_context_member_agent
        self.agent_id = 0
        self.agent_config = {}

        # Set the size policy
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        self.setSizePolicy(sizePolicy)

        # self.setMaximumHeight(400)

        self.settings_sidebar = self.Agent_Settings_SideBar(parent=self)

        self.content = QStackedWidget(self)
        self.page_general = self.Page_General_Settings(self)
        self.page_context = self.Page_Context_Settings(self)
        self.page_actions = self.Page_Actions_Settings(self)
        self.page_group = self.Page_Group_Settings(self)
        self.page_voice = self.Page_Voice_Settings(self)
        self.content.addWidget(self.page_general)
        self.content.addWidget(self.page_context)
        self.content.addWidget(self.page_actions)
        self.content.addWidget(self.page_group)
        self.content.addWidget(self.page_voice)

        # H layout for lsidebar and content
        self.input_layout = QHBoxLayout(self)
        self.input_layout.addWidget(self.settings_sidebar)
        self.input_layout.addWidget(self.content)

    def get_current_config(self):
        # Retrieve the current values from the widgets and construct a new 'config' dictionary
        current_config = {
            'general.name': self.page_general.name.text(),
            'general.avatar_path': self.page_general.avatar_path,
            'general.use_plugin': self.page_general.plugin_combo.currentData(),
            'context.model': self.page_context.model_combo.currentData(),
            'context.sys_msg': self.page_context.sys_msg.toPlainText(),
            'context.max_messages': self.page_context.max_messages.value(),
            'context.max_turns': self.page_context.max_turns.value(),
            'context.auto_title': self.page_context.auto_title.isChecked(),
            'context.display_markdown': self.page_context.display_markdown.isChecked(),
            'context.on_consecutive_response': self.page_context.on_consecutive_response.currentText(),
            'context.user_msg': self.page_context.user_msg.toPlainText(),
            'actions.enable_actions': self.page_actions.enable_actions.isChecked(),
            'actions.source_directory': self.page_actions.source_directory.text(),
            'actions.replace_busy_action_on_new': self.page_actions.replace_busy_action_on_new.isChecked(),
            'actions.use_function_calling': self.page_actions.use_function_calling.isChecked(),
            'actions.use_validator': self.page_actions.use_validator.isChecked(),
            'actions.code_auto_run_seconds': self.page_actions.code_auto_run_seconds.text(),
            'group.hide_responses': self.page_group.hide_responses.isChecked(),
            'group.output_context_placeholder': self.page_group.output_context_placeholder.text().replace('{', '').replace('}', ''),
            'group.on_multiple_inputs': self.page_group.on_multiple_inputs.currentText(),
            'group.set_members_as_user_role': self.page_group.set_members_as_user_role.isChecked(),
            'voice.current_id': int(self.page_voice.current_id),
        }
        return json.dumps(current_config)

    def update_agent_config(self):
        current_config = self.get_current_config()
        self.agent_config = json.loads(current_config)
        name = self.page_general.name.text()

        if self.is_context_member_agent:
            sql.execute("UPDATE contexts_members SET agent_config = ? WHERE id = ?", (current_config, self.agent_id))
            self.load()
        else:
            sql.execute("UPDATE agents SET config = ?, name = ? WHERE id = ?", (current_config, name, self.agent_id))
            self.parent.load()

    def load(self):
        pages = (
            self.page_general,
            self.page_context,
            self.page_actions,
            self.page_group,
            self.page_voice
        )
        for page in pages:
            page.load()

            self.settings_sidebar.load()

    class Agent_Settings_SideBar(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            # self.main = main
            self.parent = parent
            self.setObjectName("SettingsSideBarWidget")
            self.setAttribute(Qt.WA_StyledBackground, True)
            self.setProperty("class", "sidebar")

            font = QFont()
            font.setPointSize(13)  # Set font size to 20 points
            self.btn_general = self.Settings_SideBar_Button(self, text='General', font=font)
            self.btn_context = self.Settings_SideBar_Button(self, text='Context', font=font)
            self.btn_actions = self.Settings_SideBar_Button(self, text='Actions', font=font)
            self.btn_group = self.Settings_SideBar_Button(self, text='Group', font=font)
            self.btn_voice = self.Settings_SideBar_Button(self, text='Voice', font=font)
            self.btn_general.setChecked(True)

            self.layout = QVBoxLayout(self)
            self.layout.setSpacing(0)
            self.layout.setContentsMargins(0, 0, 0, 0)

            # Create a button group and add buttons to it
            self.button_group = QButtonGroup(self)
            self.button_group.addButton(self.btn_general, 0)
            self.button_group.addButton(self.btn_context, 1)
            self.button_group.addButton(self.btn_actions, 2)
            self.button_group.addButton(self.btn_group, 3)
            self.button_group.addButton(self.btn_voice, 4)  # 1

            # Connect button toggled signal
            self.button_group.buttonToggled[QAbstractButton, bool].connect(self.onButtonToggled)

            self.button_layout = QHBoxLayout()
            self.button_layout.addStretch(1)

            self.btn_pull = QPushButton(self)
            self.btn_pull.setIcon(QIcon(QPixmap(":/resources/icon-pull.png")))
            self.btn_pull.setToolTip("Set member config to agent default")
            self.button_layout.addWidget(self.btn_pull)

            self.btn_push = QPushButton(self)
            self.btn_push.setIcon(QIcon(QPixmap(":/resources/icon-push.png")))
            self.btn_push.setToolTip("Set all member configs to agent default")
            self.button_layout.addWidget(self.btn_push)

            self.button_layout.addStretch(1)

            self.warning_label = QLabel("A plugin is enabled, these settings may not work as expected")
            self.warning_label.setFixedWidth(75)
            self.warning_label.setWordWrap(True)
            self.warning_label.setStyleSheet("color: gray;")
            self.warning_label.setAlignment(Qt.AlignCenter)
            font = self.warning_label.font()
            font.setPointSize(7)
            self.warning_label.setFont(font)
            self.warning_label.hide()

            # add a 5 px spacer (not stretch)
            self.layout.addWidget(self.btn_general)
            self.layout.addWidget(self.btn_context)
            self.layout.addWidget(self.btn_actions)
            self.layout.addWidget(self.btn_group)
            self.layout.addWidget(self.btn_voice)
            self.layout.addSpacing(8)
            self.layout.addLayout(self.button_layout)
            self.layout.addStretch(1)
            self.layout.addWidget(self.warning_label)
            self.layout.addStretch(1)

        def load(self):
            self.refresh_warning_label()

            if self.parent.is_context_member_agent:
                self.btn_push.hide()
                # if context member config is not the same as agent config default, then show
                member_id = self.parent.agent_id
                default_config_str = sql.get_scalar("SELECT config FROM agents WHERE id = (SELECT agent_id FROM contexts_members WHERE id = ?)", (member_id,))
                if default_config_str is None:
                    default_config = {}
                else:
                    default_config = json.loads(default_config_str)
                member_config = self.parent.agent_config
                config_mismatch = default_config != member_config

                self.btn_pull.setVisible(config_mismatch)
            else:
                self.btn_pull.hide()
                # if any context member config is not the same as agent config default, then show

                # agent_id = self.parent.agent_id
                default_config = self.parent.agent_config

                member_configs = sql.get_results("SELECT agent_config FROM contexts_members WHERE agent_id = ?",
                                                 (self.parent.agent_id,), return_type='list')
                config_mismatch = any([json.loads(member_config) != default_config for member_config in member_configs])

                self.btn_push.setVisible(config_mismatch)

        def onButtonToggled(self, button, checked):
            if checked:
                index = self.button_group.id(button)
                self.parent.content.setCurrentIndex(index)
                # self.parent.content.currentWidget().load()
                self.refresh_warning_label()

        def refresh_warning_label(self):
            index = self.parent.content.currentIndex()
            show_plugin_warning = index > 0 and self.parent.agent_config.get('general.use_plugin', '') != ''
            if show_plugin_warning:
                self.warning_label.show()
            else:
                self.warning_label.hide()

        class Settings_SideBar_Button(QPushButton):
            def __init__(self, parent, text='', font=None):
                super().__init__(parent=parent)
                self.setProperty("class", "menuitem")

                self.setText(text)
                self.setFixedSize(75, 30)
                self.setCheckable(True)
                if font is None:
                    font = QFont()
                    font.setPointSize(13)
                self.setFont(font)

    class Page_General_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent

            main_layout = QVBoxLayout(self)
            main_layout.setAlignment(Qt.AlignCenter)

            profile_layout = QHBoxLayout()
            profile_layout.setAlignment(Qt.AlignCenter)

            self.avatar_path = ''
            self.avatar = self.ClickableAvatarLabel(self)
            self.avatar.clicked.connect(self.change_avatar)

            self.name = QLineEdit()
            self.name.textChanged.connect(parent.update_agent_config)

            font = self.name.font()
            font.setPointSize(15)
            self.name.setFont(font)

            self.name.setAlignment(Qt.AlignCenter)

            # Create a combo box for the plugin selection
            self.plugin_combo = PluginComboBox()
            self.plugin_settings = self.DynamicPluginSettings(self, self.plugin_combo)

            # # set first item text to 'No Plugin' if no plugin is selected
            # if self.plugin_combo.currentData() == '':
            #     self.plugin_combo.setItemText(0, "Choose Plugin")
            # else:
            #     self.plugin_combo.setItemText(0, "< No Plugin >")

            # Adding avatar and name to the main layout
            profile_layout.addWidget(self.avatar)  # Adding the avatar

            # add profile layout to main layout
            main_layout.addLayout(profile_layout)
            main_layout.addWidget(self.name)
            main_layout.addWidget(self.plugin_combo, alignment=Qt.AlignCenter)
            main_layout.addWidget(self.plugin_settings)
            main_layout.addStretch()

        class DynamicPluginSettings(QWidget):
            def __init__(self, parent, plugin_combo, plugin_type='agent'):
                super().__init__()
                self.parent = parent
                self.plugin_combo = plugin_combo

                self.layout = QGridLayout(self)
                self.setLayout(self.layout)
                self.plugin_combo.currentIndexChanged.connect(self.update_agent_plugin)  # update_agent_config)

            def update_agent_plugin(self):
                from agentpilot.context.base import Context
                main = self.parent.parent.main
                main.page_chat.context = Context(main)
                self.parent.parent.update_agent_config()

            def load(self):
                agent_class = get_plugin_agent_class(self.plugin_combo.currentData(), None)
                if agent_class is None:
                    self.hide()
                    return

                ext_params = getattr(agent_class, 'extra_params', [])

                # Only use one column if there are fewer than 7 params,
                # otherwise use two columns as before.
                if len(ext_params) < 7:
                    widgets_per_column = len(ext_params)
                else:
                    widgets_per_column = len(ext_params) // 2 + len(ext_params) % 2

                self.clear_layout()
                row, col = 0, 0
                for i, (param_name, param_type, default_value) in enumerate(ext_params):
                    widget = self.create_widget_by_type(param_type, default_value)
                    setattr(self, param_name, widget)

                    param_name = param_name
                    param_label = QLabel(param_name)
                    param_label.setAlignment(Qt.AlignRight)
                    self.layout.addWidget(param_label, row, col * 2)
                    self.layout.addWidget(widget, row, col * 2 + 1)

                    row += 1
                    # Adjust column wrapping based on whether a single or dual column layout is used
                    if row >= widgets_per_column:
                        row = 0
                        col += 1

                self.show()

            def create_widget_by_type(self, param_type, default_value):

                width = 50
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
                    widget = QLineEdit()
                    widget.setText(default_value)
                elif isinstance(param_type, tuple):
                    widget = CComboBox()
                    widget.addItems(param_type)
                    widget.setCurrentText(default_value)
                    width = 150
                else:
                    raise ValueError(f'Unknown param type: {param_type}')

                widget.setFixedWidth(width)
                # widget.valueChanged.connect(self.parent.parent.update_agent_config)
                return widget

            def clear_layout(self):
                for i in reversed(range(self.layout.count())):
                    widget = self.layout.itemAt(i).widget()
                    if widget is not None:
                        widget.deleteLater()

        def load(self):
            with block_signals(self):
                self.avatar_path = self.parent.agent_config.get('general.avatar_path', '')
                diameter = self.avatar.width()
                avatar_img = path_to_pixmap(self.avatar_path, diameter=diameter)

                self.avatar.setPixmap(avatar_img)
                self.avatar.update()

                self.name.setText(self.parent.agent_config.get('general.name', ''))

                active_plugin = self.parent.agent_config.get('general.use_plugin', '')
                for i in range(self.plugin_combo.count()):  # todo dirty
                    if self.plugin_combo.itemData(i) == active_plugin:
                        self.plugin_combo.setCurrentIndex(i)
                        break
                else:
                    self.plugin_combo.setCurrentIndex(0)
                self.plugin_settings.load()

        # def plugin_changed(self):
        #     self.parent.update_agent_config()

        class ClickableAvatarLabel(QLabel):
            clicked = Signal()

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.setAlignment(Qt.AlignCenter)
                self.setCursor(Qt.PointingHandCursor)
                self.setFixedSize(100, 100)
                self.setStyleSheet(
                    "border: 1px dashed rgb(200, 200, 200); border-radius: 50px;")  # A custom style for the empty label

            def mousePressEvent(self, event):
                super().mousePressEvent(event)
                if event.button() == Qt.LeftButton:
                    self.clicked.emit()

            def setPixmap(self, pixmap):
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
            filename, _ = QFileDialog.getOpenFileName(self, "QFileDialog.getOpenFileName()", "",
                                                      "Images (*.png *.jpeg *.jpg *.bmp *.gif)", options=options)
            PIN_STATE = current_pin_state
            if filename:
                filename = filename
                print('change_avatar, simplified fn: ', filename)
                self.avatar.setPixmap(QPixmap(filename))

                simp_path = simplify_path(filename)
                print(f'Simplified {filename} to {simp_path}')
                self.avatar_path = simplify_path(filename)
                self.parent.update_agent_config()

    class Page_Context_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent

            self.form_layout = QFormLayout()

            self.model_combo = ModelComboBox()
            self.model_combo.setFixedWidth(150)

            self.auto_title = QCheckBox()
            self.auto_title.setFixedWidth(30)
            # self.form_layout.addRow(QLabel('Auto title:'), self.auto_title)

            # Create a QHBoxLayout and add max_messages and auto_title to it
            self.model_and_auto_title_layout = QHBoxLayout()
            self.model_and_auto_title_layout.setSpacing(70)
            self.model_and_auto_title_layout.addWidget(QLabel('Model:'))
            self.model_and_auto_title_layout.addWidget(self.model_combo)
            self.model_and_auto_title_layout.addWidget(QLabel('Auto title:'))
            self.model_and_auto_title_layout.addWidget(self.auto_title)

            # Add the QHBoxLayout to the form layout
            self.form_layout.addRow(self.model_and_auto_title_layout)

            self.sys_msg = QTextEdit()
            self.sys_msg.setFixedHeight(140)
            self.form_layout.addRow(QLabel('System message:'), self.sys_msg)

            self.max_messages = QSpinBox()
            self.max_messages.setFixedWidth(60)  # Consistent width
            # self.form_layout.addRow(QLabel('Max messages:'), self.max_messages)

            display_markdown_label = QLabel('Display markdown:')
            display_markdown_label.setFixedWidth(100)
            self.display_markdown = QCheckBox()
            self.display_markdown.setFixedWidth(30)
            # self.form_layout.addRow(QLabel('Display markdown:'), self.display_markdown)
            self.max_msgs_and_markdown_layout = QHBoxLayout()
            self.max_msgs_and_markdown_layout.setSpacing(10)
            self.max_msgs_and_markdown_layout.addWidget(QLabel('Max messages:'))
            self.max_msgs_and_markdown_layout.addWidget(self.max_messages)
            self.max_msgs_and_markdown_layout.addStretch(1)
            self.max_msgs_and_markdown_layout.addWidget(QLabel('Display markdown:'))
            self.max_msgs_and_markdown_layout.addWidget(self.display_markdown)

            # Add the QHBoxLayout to the form layout
            self.form_layout.addRow(self.max_msgs_and_markdown_layout)

            self.max_turns_and_consec_response_layout = QHBoxLayout()
            self.max_turns_and_consec_response_layout.setSpacing(10)
            self.max_turns_and_consec_response_layout.addStretch(1)
            self.max_turns_and_consec_response_layout.addWidget(QLabel('Max turns:'))
            self.max_turns = QSpinBox()
            self.max_turns.setFixedWidth(60)
            self.max_turns_and_consec_response_layout.addWidget(self.max_turns)

            self.max_turns_and_consec_response_layout.addStretch(1)

            self.max_turns_and_consec_response_layout.addWidget(QLabel('Consecutive responses:'))
            self.on_consecutive_response = CComboBox()
            self.on_consecutive_response.addItems(['PAD', 'REPLACE', 'NOTHING'])
            self.on_consecutive_response.setFixedWidth(90)
            self.max_turns_and_consec_response_layout.addWidget(self.on_consecutive_response)
            self.form_layout.addRow(self.max_turns_and_consec_response_layout)

            self.user_msg = QTextEdit()
            # set placeholder text with grey color
            self.user_msg.setFixedHeight(80)  # Adjust height as per requirement
            self.form_layout.addRow(QLabel('User message:'), self.user_msg)

            # Add the form layout to a QVBoxLayout and add a spacer to push everything to the top
            self.main_layout = QVBoxLayout(self)
            self.main_layout.addLayout(self.form_layout)
            spacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
            self.main_layout.addItem(spacer)

            self.model_combo.currentIndexChanged.connect(parent.update_agent_config)
            self.auto_title.stateChanged.connect(parent.update_agent_config)
            self.sys_msg.textChanged.connect(parent.update_agent_config)
            self.display_markdown.stateChanged.connect(parent.update_agent_config)
            self.max_messages.valueChanged.connect(parent.update_agent_config)
            self.max_turns.valueChanged.connect(parent.update_agent_config)
            self.on_consecutive_response.currentIndexChanged.connect(parent.update_agent_config)
            self.user_msg.textChanged.connect(parent.update_agent_config)

        def load(self):
            parent = self.parent
            with block_signals(self):
                self.model_combo.load()

                # Save current position
                sys_msg_cursor_pos = self.sys_msg.textCursor().position()
                user_msg_cursor_pos = self.user_msg.textCursor().position()

                model_name = parent.agent_config.get('context.model', '')
                index = self.model_combo.findData(model_name)
                self.model_combo.setCurrentIndex(index)

                self.auto_title.setChecked(parent.agent_config.get('context.auto_title', True))
                self.sys_msg.setText(parent.agent_config.get('context.sys_msg', ''))
                # self.fallback_to_davinci.setChecked(parent.agent_config.get('context.fallback_to_davinci', False))
                self.max_messages.setValue(parent.agent_config.get('context.max_messages', 5))
                self.display_markdown.setChecked(parent.agent_config.get('context.display_markdown', False))
                self.max_turns.setValue(parent.agent_config.get('context.max_turns', 5))
                self.on_consecutive_response.setCurrentText(
                    parent.agent_config.get('context.on_consecutive_response', 'REPLACE'))
                self.user_msg.setText(parent.agent_config.get('context.user_msg', ''))

                # Restore cursor position
                sys_msg_cursor = self.sys_msg.textCursor()
                sys_msg_cursor.setPosition(sys_msg_cursor_pos)
                self.sys_msg.setTextCursor(sys_msg_cursor)

                user_msg_cursor = self.user_msg.textCursor()
                user_msg_cursor.setPosition(user_msg_cursor_pos)
                self.user_msg.setTextCursor(user_msg_cursor)

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
            # self.form_layout.addRow(self.label_use_function_calling, self.use_function_calling)

            # Create the combo box and add the items
            self.function_calling_mode = CComboBox()
            self.function_calling_mode.addItems(['ISOLATED', 'INTEGRATED'])
            # self.form_layout.addRow(QLabel('Function Calling Mode:'), self.function_calling_mode)

            # Create a new horizontal layout to include the check box and the combo box
            function_calling_layout = QHBoxLayout()
            function_calling_layout.addWidget(self.use_function_calling)
            function_calling_layout.addWidget(self.function_calling_mode)
            function_calling_layout.addStretch(1)

            # Make the combo box initially hidden
            self.function_calling_mode.setVisible(False)
            self.function_calling_mode.setFixedWidth(150)
            self.form_layout.addRow(self.label_use_function_calling, function_calling_layout)

            self.use_validator = QCheckBox()
            self.form_layout.addRow(self.label_use_validator, self.use_validator)

            self.code_auto_run_seconds = QLineEdit()
            self.code_auto_run_seconds.setValidator(QIntValidator(0, 300))
            self.form_layout.addRow(self.label_code_auto_run_seconds, self.code_auto_run_seconds)

            self.setLayout(self.form_layout)

            # Connect the 'stateChanged' signal of 'use_function_calling' to a new method
            self.use_function_calling.stateChanged.connect(self.toggle_function_calling_type_visibility())

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
                self.replace_busy_action_on_new.setChecked(
                    parent.agent_config.get('actions.replace_busy_action_on_new', False))
                self.use_function_calling.setChecked(parent.agent_config.get('actions.use_function_calling', False))
                self.use_validator.setChecked(parent.agent_config.get('actions.use_validator', False))
                self.code_auto_run_seconds.setText(str(parent.agent_config.get('actions.code_auto_run_seconds', 5)))

            self.toggle_enabled_state()
            self.toggle_function_calling_type_visibility()

        def browse_for_folder(self):
            folder = QFileDialog.getExistingDirectory(self, "Select Source Directory")
            if folder:
                self.source_directory.setText(folder)

        def toggle_enabled_state(self):
            global TEXT_COLOR
            is_enabled = self.enable_actions.isChecked()

            self.source_directory.setEnabled(is_enabled)
            self.browse_button.setEnabled(is_enabled)
            self.replace_busy_action_on_new.setEnabled(is_enabled)
            self.use_function_calling.setEnabled(is_enabled)
            self.use_validator.setEnabled(is_enabled)

            if is_enabled:
                color = TEXT_COLOR
            else:
                color = "#4d4d4d"

            self.label_source_directory.setStyleSheet(f"color: {color}")
            self.label_replace_busy_action_on_new.setStyleSheet(f"color: {color}")
            self.label_use_function_calling.setStyleSheet(f"color: {color}")
            self.label_use_validator.setStyleSheet(f"color: {color}")

        def toggle_function_calling_type_visibility(self):
            self.function_calling_mode.setVisible(self.use_function_calling.isChecked())

    class Page_Group_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent

            self.form_layout = QFormLayout(self)

            self.label_hide_responses = QLabel('Hide responses:')
            self.label_output_context_placeholder = QLabel('Output context placeholder:')

            self.hide_responses = QCheckBox()
            self.form_layout.addRow(self.label_hide_responses, self.hide_responses)

            self.output_context_placeholder = QLineEdit()
            self.form_layout.addRow(self.label_output_context_placeholder, self.output_context_placeholder)

            self.on_multiple_inputs = CComboBox()
            self.on_multiple_inputs.setFixedWidth(170)
            self.on_multiple_inputs.addItems(['Use system message', 'Combined user message'])
            self.form_layout.addRow(QLabel('On multiple inputs:'), self.on_multiple_inputs)

            # add checkbox for 'Show members as user role
            self.set_members_as_user_role = QCheckBox()
            self.form_layout.addRow(QLabel('Show members as user role:'), self.set_members_as_user_role)

            self.hide_responses.stateChanged.connect(parent.update_agent_config)
            self.output_context_placeholder.textChanged.connect(parent.update_agent_config)
            self.on_multiple_inputs.currentIndexChanged.connect(parent.update_agent_config)
            self.set_members_as_user_role.stateChanged.connect(parent.update_agent_config)

        def load(self):
            parent = self.parent
            with block_signals(self):
                self.hide_responses.setChecked(parent.agent_config.get('group.hide_responses', False))
                self.output_context_placeholder.setText(
                    str(parent.agent_config.get('group.output_context_placeholder', '')))
                self.on_multiple_inputs.setCurrentText(
                    parent.agent_config.get('group.on_multiple_inputs', 'Use system message'))
                self.set_members_as_user_role.setChecked(
                    parent.agent_config.get('group.set_members_as_user_role', True))

    class Page_Voice_Settings(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.layout = QVBoxLayout(self)

            # Search panel setup
            self.search_panel = QWidget(self)
            self.search_layout = QHBoxLayout(self.search_panel)
            self.api_dropdown = APIComboBox(self, first_item='ALL')
            self.search_field = QLineEdit(self)
            self.search_layout.addWidget(QLabel("API:"))
            self.search_layout.addWidget(self.api_dropdown)
            self.search_layout.addWidget(QLabel("Search:"))
            self.search_layout.addWidget(self.search_field)
            self.layout.addWidget(self.search_panel)

            self.table = BaseTableWidget(self)

            # Creating a new QWidget to hold the buttons
            self.buttons_panel = QWidget(self)
            self.buttons_layout = QHBoxLayout(self.buttons_panel)
            self.buttons_layout.setAlignment(Qt.AlignRight)

            # Set as voice button
            self.set_voice_button = QPushButton("Set as voice", self)
            self.set_voice_button.setFixedWidth(150)

            # Test voice button
            self.test_voice_button = QPushButton("Test voice", self)
            self.test_voice_button.setFixedWidth(150)

            # Adding buttons to the layout
            self.buttons_layout.addWidget(self.set_voice_button)
            self.buttons_layout.addWidget(self.test_voice_button)
            self.layout.addWidget(self.table)
            self.layout.addWidget(self.buttons_panel)

            self.set_voice_button.clicked.connect(self.set_as_voice)
            self.test_voice_button.clicked.connect(self.test_voice)

            self.api_dropdown.currentIndexChanged.connect(self.filter_table)
            self.search_field.textChanged.connect(self.filter_table)

            self.load_data_from_db()
            self.current_id = 0

        def load(self):  # Load Voices
            # Database fetch and display
            with block_signals(self):
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

        def highlight_and_select_current_voice(self):
            # if not self.current_id or self.current_id == 0:
            #     return

            # Prepare font outside the loop
            normal_font = self.table.font()
            highlighted_font = QFont(normal_font)
            highlighted_font.setUnderline(True)
            highlighted_font.setBold(True)

            for row_index in range(self.table.rowCount()):
                item_id = int(self.table.item(row_index, 0).text())
                is_current = (item_id == self.current_id)
                font = highlighted_font if is_current else normal_font

                for col_index in range(self.table.columnCount()):
                    item = self.table.item(row_index, col_index)
                    item.setFont(font)

                if is_current:
                    self.table.selectRow(row_index)
                    self.table.scrollToItem(self.table.item(row_index, 0))

        def filter_table(self):
            api_name = self.api_dropdown.currentText().lower()
            search_text = self.search_field.text().lower()

            # Define the filtering criteria as a function
            def matches_filter(voice):
                name, known_from = voice[2].lower(), voice[3].lower()
                return (api_name == 'all' or api_name in name) and (
                        search_text in name or search_text in known_from)

            filtered_voices = filter(matches_filter, self.all_voices)
            self.display_data_in_table(list(filtered_voices))

        def display_data_in_table(self, voices):
            # Add a row for each voice
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

            new_voice_id = int(self.table.item(current_row, 0).text())
            if new_voice_id == self.current_id:
                new_voice_id = 0
            self.current_id = new_voice_id
            self.parent.update_agent_config()  # 'voice.current_id', voice_id)
            # self.parent.main.page_chat.load()
            # self.load()
            # self.parent.update_agent_config()
            # Further actions can be taken using voice_id or the data of the selected row
            # QMessageBox.information(self, "Voice Set", f"Voice with ID {self.current_id} has been set!")

        def test_voice(self):
            # todo - Implement functionality to test the voice
            pass


class Page_Agents(ContentPage):
    def __init__(self, main):
        super().__init__(main=main, title='Agents')
        self.main = main

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

        # Connect the double-click signal with the chat button click
        self.table_widget.itemDoubleClicked.connect(self.on_row_double_clicked)

        self.agent_settings = AgentSettings(self)

        # Add table and container to the layout
        self.layout.addWidget(self.table_widget)
        self.layout.addWidget(self.agent_settings)

    def load(self):  # Load agents
        icon_chat = QIcon(':/resources/icon-chat.png')
        icon_del = QIcon(':/resources/icon-delete.png')

        with block_signals(self):
            self.table_widget.setRowCount(0)
            data = sql.get_results("""
                SELECT
                    id,
                    '' AS avatar,
                    config,
                    '' AS name,
                    '' AS chat_button,
                    '' AS del_button
                FROM agents
                ORDER BY id DESC""")
            for row_data in data:
                row_data = list(row_data)
                r_config = json.loads(row_data[2])
                row_data[3] = r_config.get('general.name', 'Assistant')

                row_position = self.table_widget.rowCount()
                self.table_widget.insertRow(row_position)
                for column, item in enumerate(row_data):
                    self.table_widget.setItem(row_position, column, QTableWidgetItem(str(item)))

                # Parse the config JSON to get the avatar path
                agent_avatar_path = r_config.get('general.avatar_path', '')
                pixmap = path_to_pixmap(agent_avatar_path, diameter=25)

                # Create a QLabel to hold the pixmap
                avatar_label = QLabel()
                avatar_label.setPixmap(pixmap)
                # set background to transparent
                avatar_label.setAttribute(Qt.WA_TranslucentBackground, True)

                # Add the new avatar icon column after the ID column
                self.table_widget.setCellWidget(row_position, 1, avatar_label)

                btn_chat = QPushButton('')
                btn_chat.setIcon(icon_chat)
                btn_chat.setIconSize(QSize(25, 25))
                # set background to transparent
                # set background to white at 30% opacity when hovered
                btn_chat.setStyleSheet("QPushButton { background-color: transparent; }"
                                       "QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); }")
                btn_chat.clicked.connect(partial(self.on_chat_btn_clicked, row_data))
                self.table_widget.setCellWidget(row_position, 4, btn_chat)

                btn_del = QPushButton('')
                btn_del.setIcon(icon_del)
                btn_del.setIconSize(QSize(25, 25))
                btn_del.setStyleSheet("QPushButton { background-color: transparent; }"
                                      "QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); }")
                btn_del.clicked.connect(partial(self.delete_agent, row_data))
                self.table_widget.setCellWidget(row_position, 5, btn_del)

        if self.agent_settings.agent_id > 0:
            for row in range(self.table_widget.rowCount()):
                if self.table_widget.item(row, 0).text() == str(self.agent_settings.agent_id):
                    self.table_widget.selectRow(row)
                    break
        else:
            if self.table_widget.rowCount() > 0:
                self.table_widget.selectRow(0)

    def on_row_double_clicked(self, item):
        id = self.table_widget.item(item.row(), 0).text()
        self.chat_with_agent(id)

    def on_agent_selected(self):
        current_row = self.table_widget.currentRow()
        if current_row == -1: return
        sel_id = self.table_widget.item(current_row, 0).text()
        agent_config_json = sql.get_scalar('SELECT config FROM agents WHERE id = ?', (sel_id,))

        self.agent_settings.agent_id = int(self.table_widget.item(current_row, 0).text())
        self.agent_settings.agent_config = json.loads(agent_config_json) if agent_config_json else {}
        self.agent_settings.load()

    def on_chat_btn_clicked(self, row_data):
        id_value = row_data[0]  # self.table_widget.item(row_item, 0).text()
        self.chat_with_agent(id_value)

    def chat_with_agent(self, id):
        if self.main.page_chat.context.responding:
            return
        self.main.page_chat.new_context(agent_id=id)
        self.main.content.setCurrentWidget(self.main.page_chat)
        self.main.sidebar.btn_new_context.setChecked(True)

    def delete_agent(self, row_data):
        global PIN_STATE
        context_count = sql.get_scalar("""
            SELECT
                COUNT(*)
            FROM contexts_members
            WHERE agent_id = ?""", (row_data[0],))

        if context_count > 0:
            retval = display_messagebox(
                icon=QMessageBox.Warning,
                text=f"Cannot delete '{row_data[3]}' because they exist in {context_count} contexts.",
                title="Warning",
                buttons=QMessageBox.Ok
            )
        else:
            retval = display_messagebox(
                icon=QMessageBox.Warning,
                text="Are you sure you want to delete this agent?",
                title="Delete Agent",
                buttons=QMessageBox.Yes | QMessageBox.No
            )

        # current_pin_state = PIN_STATE
        # PIN_STATE = True
        # retval = msg.exec_()
        # PIN_STATE = current_pin_state

        if retval != QMessageBox.Yes:
            return

        # sql.execute("DELETE FROM contexts_messages WHERE context_id IN (SELECT id FROM contexts WHERE agent_id = ?);", (row_data[0],))
        # sql.execute("DELETE FROM contexts WHERE agent_id = ?;", (row_data[0],))
        # sql.execute('DELETE FROM contexts_members WHERE context_id = ?', (row_data[0],))
        sql.execute("DELETE FROM agents WHERE id = ?;", (row_data[0],))
        self.load()

    class Button_New_Agent(QPushButton):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.clicked.connect(self.new_agent)
            self.icon = QIcon(QPixmap(":/resources/icon-new.png"))
            self.setIcon(self.icon)
            self.setFixedSize(25, 25)
            self.setIconSize(QSize(18, 18))
            self.input_dialog = None

        def new_agent(self):
            global PIN_STATE
            current_pin_state = PIN_STATE
            PIN_STATE = True
            self.input_dialog = QInputDialog(self)
            text, ok = self.input_dialog.getText(self, 'New Agent', 'Enter a name for the agent:')

            if ok:
                global_config_str = sql.get_scalar("SELECT value FROM settings WHERE field = 'global_config'")
                global_conf = json.loads(global_config_str)
                global_conf['general.name'] = text
                global_config_str = json.dumps(global_conf)
                try:
                    sql.execute("INSERT INTO `agents` (`name`, `config`) SELECT ?, ?",
                                (text, global_config_str))
                    self.parent.load()
                except IntegrityError:
                    QMessageBox.warning(self, "Duplicate Agent Name", "An agent with this name already exists.")

            PIN_STATE = current_pin_state


class Page_Contexts(ContentPage):
    def __init__(self, main):
        super().__init__(main=main, title='Contexts')
        self.main = main

        self.table_widget = BaseTableWidget(self)
        self.table_widget.setColumnCount(5)

        self.table_widget.setColumnWidth(3, 45)
        self.table_widget.setColumnWidth(4, 45)
        self.table_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        self.table_widget.hideColumn(0)
        self.table_widget.horizontalHeader().hide()

        # remove visual cell selection and only select row
        self.table_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectRows)

        # Connect the double-click signal with the chat button click
        self.table_widget.itemDoubleClicked.connect(self.on_row_double_clicked)

        # Add the table to the layout
        self.layout.addWidget(self.table_widget)

        # Enable the context menu on the table widget
        self.table_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.table_widget.itemChanged.connect(self.item_edited)

    def show_context_menu(self, position):
        menu = QMenu(self)

        # Add actions to the context menu
        rename_action = menu.addAction('Rename')
        chat_action = menu.addAction('Chat')
        delete_action = menu.addAction('Delete')

        # Get the selected row's index
        selected_row_index = self.table_widget.indexAt(position).row()
        if selected_row_index < 0:
            return

        # Retrieve the row data as a tuple
        row_data = tuple(
            self.table_widget.item(selected_row_index, col).text() for col in range(self.table_widget.columnCount()))

        # Connect the actions to specific methods
        rename_action.triggered.connect(partial(self.rename_context, selected_row_index))
        chat_action.triggered.connect(partial(self.on_chat_btn_clicked, row_data))
        delete_action.triggered.connect(partial(self.delete_context, row_data))

        # Execute the menu
        menu.exec_(self.table_widget.viewport().mapToGlobal(position))

    def load(self):  # Load Contexts
        self.table_widget.setRowCount(0)
        data = sql.get_results("""
            SELECT
                c.id,
                c.summary,
                group_concat(a.name, ' + ') as name,
                '' AS goto_button,
                '' AS del_button
            FROM contexts c
            LEFT JOIN contexts_members cp
                ON c.id = cp.context_id
            LEFT JOIN agents a
                ON cp.agent_id = a.id
            LEFT JOIN (
                SELECT
                    context_id,
                    MAX(id) as latest_message_id
                FROM contexts_messages
                GROUP BY context_id
            ) cm ON c.id = cm.context_id
            WHERE c.parent_id IS NULL
            GROUP BY c.id
            ORDER BY
                COALESCE(cm.latest_message_id, 0) DESC, 
                c.id DESC;
            """)
        # first_desc = 'CURRENT CONTEXT'

        icon_chat = QIcon(':/resources/icon-chat.png')
        icon_del = QIcon(':/resources/icon-delete.png')

        for row_data in data:
            row_position = self.table_widget.rowCount()
            self.table_widget.insertRow(row_position)
            for column, item in enumerate(row_data):
                self.table_widget.setItem(row_position, column, QTableWidgetItem(str(item)))

            if row_data[2] is None:  # If agent_name is NULL
                self.table_widget.setSpan(row_position, 1, 1, 2)  # Make the summary cell span over the next column

            btn_chat = QPushButton('')
            btn_chat.setIcon(icon_chat)
            btn_chat.setIconSize(QSize(25, 25))
            btn_chat.setStyleSheet("QPushButton { background-color: transparent; }"
                                   "QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); }")

            btn_chat.clicked.connect(partial(self.on_chat_btn_clicked, row_data))
            self.table_widget.setCellWidget(row_position, 3, btn_chat)

            btn_delete = QPushButton('')
            btn_delete.setIcon(icon_del)
            btn_delete.setIconSize(QSize(25, 25))
            btn_delete.setStyleSheet("QPushButton { background-color: transparent; }"
                                     "QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); }")

            btn_delete.clicked.connect(partial(self.delete_context, row_data))
            self.table_widget.setCellWidget(row_position, 4, btn_delete)

    def on_row_double_clicked(self, item):
        id = self.table_widget.item(item.row(), 0).text()
        self.chat_with_context(id)

    def on_chat_btn_clicked(self, row_data):
        id_value = row_data[0]  # self.table_widget.item(row_item, 0).text()
        self.chat_with_context(id_value)

    def chat_with_context(self, id):
        if self.main.page_chat.context.responding:
            return
        self.main.page_chat.goto_context(context_id=id)
        self.main.content.setCurrentWidget(self.main.page_chat)
        self.main.sidebar.btn_new_context.setChecked(True)

    def rename_context(self, row_item):
        # start editting the summary cell
        self.table_widget.editItem(self.table_widget.item(row_item, 1))

    def item_edited(self, item):
        row = item.row()
        context_id = self.table_widget.item(row, 0).text()

        id_map = {
            1: 'summary',
        }

        column = item.column()
        if column not in id_map:
            return
        column_name = id_map.get(column)
        new_value = item.text()
        sql.execute(f"""
            UPDATE contexts
            SET {column_name} = ?
            WHERE id = ?
        """, (new_value, context_id,))

    def delete_context(self, row_item):
        from agentpilot.context.base import Context

        retval = display_messagebox(
            icon=QMessageBox.Warning,
            text="Are you sure you want to permanently delete this context?",
            title="Delete Context",
            buttons=QMessageBox.Yes | QMessageBox.No
        )
        if retval != QMessageBox.Yes:
            return

        context_id = row_item[0]
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

        self.load()

        if self.main.page_chat.context.id == context_id:
            self.main.page_chat.context = Context(main=self.main)


class Page_Chat(QScrollArea):
    def __init__(self, main):
        super().__init__(parent=main)
        from agentpilot.context.base import Context

        self.main = main
        self.context = Context(main=self.main)

        self.threadpool = QThreadPool()
        self.chat_bubbles = []
        self.last_member_msgs = {}

        # Overall layout for the page
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # TopBar pp
        self.topbar = self.Top_Bar(self)
        self.layout.addWidget(self.topbar)

        # Scroll area for the chat
        self.scroll_area = QScrollArea(self)
        self.chat = QWidget(self.scroll_area)
        self.chat_scroll_layout = QVBoxLayout(self.chat)
        # self.chat_scroll_layout.setSpacing(0)
        self.chat_scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_scroll_layout.addStretch(1)

        self.scroll_area.setWidget(self.chat)
        self.scroll_area.setWidgetResizable(True)

        self.layout.addWidget(self.scroll_area)
        # self.layout.addStretch(1)

        self.installEventFilterRecursively(self)
        self.temp_text_size = None
        self.decoupled_scroll = False

    def load(self):
        self.clear_bubbles()
        self.context.load()
        self.refresh()

    def load_context(self):
        from agentpilot.context.base import Context
        context_id = self.context.id if self.context else None
        self.context = Context(main=self.main, context_id=context_id)

    # def reload(self):
    #     # text_cursors = self.get_text_cursors()
    #     self.refresh()
    #     # self.apply_text_cursors(text_cursors)

    def refresh(self):
        # iterate chat_bubbles backwards and remove any that have id = -1
        for i in range(len(self.chat_bubbles) - 1, -1, -1):
            if self.chat_bubbles[i].bubble.msg_id == -1:
                self.chat_bubbles.pop(i).deleteLater()

        last_container = self.chat_bubbles[-1] if self.chat_bubbles else None
        last_bubble_msg_id = last_container.bubble.msg_id if last_container else 0

        # get scroll position
        scroll_bar = self.scroll_area.verticalScrollBar()

        scroll_pos = scroll_bar.value()

        # self.context.message_history.load()
        for msg in self.context.message_history.messages:
            if msg.id <= last_bubble_msg_id:
                continue
            self.insert_bubble(msg)

        # load the top bar
        self.topbar.load()

        # if last bubble is code then start timer
        if self.chat_bubbles:
            last_bubble = self.chat_bubbles[-1].bubble
            if last_bubble.role == 'code':
                last_bubble.start_timer()

        # restore scroll position
        scroll_bar.setValue(scroll_pos)

    def clear_bubbles(self):
        while self.chat_bubbles:
            bubble = self.chat_bubbles.pop()
            self.chat_scroll_layout.removeWidget(bubble)
            bubble.deleteLater()

    # def get_text_cursors(self):
    #     text_cursors = {}
    #     for cont in self.chat_bubbles:
    #         bubble = cont.bubble
    #         bubble_cursor = bubble.textCursor()
    #         if not bubble_cursor.hasSelection():
    #             continue
    #         text_cursors[bubble.msg_id] = bubble_cursor
    #     return text_cursors
    #
    # def apply_text_cursors(self, text_cursors):
    #     if not text_cursors:
    #         return
    #     for cont in self.chat_bubbles:
    #         bubble = cont.bubble
    #         if bubble.msg_id in text_cursors:
    #             bubble.setTextCursor(text_cursors[bubble.msg_id])
    ##############################

    # def load(self):
    #     # store existing textcursors for each textarea
    #     textcursors = {}
    #     for cont in self.chat_bubbles:
    #         bubble = cont.bubble
    #         bubble_cursor = bubble.textCursor()
    #         if not bubble_cursor.hasSelection():
    #             continue
    #         textcursors[bubble.msg_id] = bubble_cursor
    #
    #     # self.clear_bubbles()
    #     while self.chat_bubbles:
    #         bubble = self.chat_bubbles.pop()
    #         self.chat_scroll_layout.removeWidget(bubble)
    #         bubble.deleteLater()
    #     self.reload(textcursors=textcursors)

    # def reload(self, textcursors=None):
    #     self.context.load()
    #
    #     # get scroll position
    #     scroll_bar = self.scroll_area.verticalScrollBar()
    #     scroll_pos = scroll_bar.value()
    #
    #     last_container = self.chat_bubbles[-1] if self.chat_bubbles else None
    #     last_bubble_msg_id = last_container.bubble.msg_id if last_container else 0
    #     messages = self.context.message_history.messages
    #     for msg in messages:
    #         if msg.id <= last_bubble_msg_id:
    #             continue
    #         self.insert_bubble(msg)
    #
    #     if textcursors:
    #         for cont in self.chat_bubbles:
    #             bubble = cont.bubble
    #             if bubble.msg_id in textcursors:
    #                 bubble.setTextCursor(textcursors[bubble.msg_id])
    #
    #     self.topbar.load()
    #
    #     # if last bubble is code then start timer
    #     if self.chat_bubbles:
    #         last_bubble = self.chat_bubbles[-1].bubble
    #         if last_bubble.role == 'code':
    #             last_bubble.start_timer()
    #
    #     # restore scroll position
    #     scroll_bar.setValue(scroll_pos)
    #     # scroll_bar.setValue(scroll_bar.maximum())
    #     # if not self.decoupled_scroll:
    #     #     self.scroll_to_end()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Wheel:
            if event.modifiers() & Qt.ControlModifier:
                delta = event.angleDelta().y()

                if delta > 0:
                    self.temp_zoom_in()
                else:
                    self.temp_zoom_out()

                return True  # Stop further propagation of the wheel event
            else:
                is_generating = self.context.responding  # self.threadpool.activeThreadCount() > 0
                if is_generating:
                    scroll_bar = self.scroll_area.verticalScrollBar()
                    is_at_bottom = scroll_bar.value() >= scroll_bar.maximum() - 10
                    if not is_at_bottom:
                        self.decoupled_scroll = True
                    else:
                        self.decoupled_scroll = False

        if event.type() == QEvent.KeyRelease:
            if event.key() == Qt.Key_Control:
                self.update_text_size()

                return True  # Stop further propagation of the wheel event

        return super().eventFilter(watched, event)

    def temp_zoom_in(self):
        if not self.temp_text_size:
            self.temp_text_size = config.get_value('display.text_size')
        if self.temp_text_size >= 50:
            return
        self.temp_text_size += 1
        # self.main.page_settings.update_config('display.text_size', self.temp_text_size)
        # self.refresh()  # todo instead of reloading bubbles just reapply style
        # self.setFocus()

    def temp_zoom_out(self):
        if not self.temp_text_size:
            self.temp_text_size = config.get_value('display.text_size')
        if self.temp_text_size <= 7:
            return
        self.temp_text_size -= 1
        # self.main.page_settings.update_config('display.text_size', self.temp_text_size)
        # self.refresh()  # todo instead of reloading bubbles just reapply style
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

    # If only one agent, hide the graphics scene and show agent settings
    class Top_Bar(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.setMouseTracking(True)

            self.settings_layout = QVBoxLayout(self)
            self.settings_layout.setSpacing(0)
            self.settings_layout.setContentsMargins(0, 0, 0, 0)

            input_container = QWidget()
            input_container.setFixedHeight(40)
            self.topbar_layout = QHBoxLayout(input_container)
            self.topbar_layout.setSpacing(0)
            self.topbar_layout.setContentsMargins(5, 5, 5, 10)

            self.settings_open = False
            self.group_settings = GroupSettings(self)
            self.group_settings.hide()

            self.settings_layout.addWidget(input_container)
            self.settings_layout.addWidget(self.group_settings)
            # self.settings_layout.addStretch(1)

            self.profile_pic_label = QLabel(self)
            self.profile_pic_label.setFixedSize(45, 30)

            self.topbar_layout.addWidget(self.profile_pic_label)
            # connect profile label click to method 'open'
            self.profile_pic_label.mousePressEvent = self.agent_name_clicked

            self.agent_name_label = QLabel(self)

            font = self.agent_name_label.font()
            font.setPointSize(15)
            self.agent_name_label.setFont(font)
            self.agent_name_label.setStyleSheet("QLabel { color: #b3ffffff; }"
                                                "QLabel:hover { color: #ccffffff; }")
            self.agent_name_label.mousePressEvent = self.agent_name_clicked
            self.agent_name_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

            self.topbar_layout.addWidget(self.agent_name_label)

            self.title_label = QLineEdit(self)
            small_font = self.title_label.font()
            small_font.setPointSize(10)
            self.title_label.setFont(small_font)
            self.title_label.setStyleSheet("QLineEdit { color: #80ffffff; }"
                                           "QLineEdit:hover { color: #99ffffff; }")
            self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.title_label.textChanged.connect(self.title_edited)

            self.topbar_layout.addWidget(self.title_label)

            # self.topbar_layout.addStretch(1)

            self.button_container = QWidget(self)
            button_layout = QHBoxLayout(self.button_container)
            button_layout.setSpacing(5)
            button_layout.setContentsMargins(0, 0, 20, 0)

            # Create buttons
            self.btn_prev_context = QPushButton()
            self.btn_next_context = QPushButton()
            self.btn_prev_context.setIcon(QIcon(':/resources/icon-left-arrow.png'))
            self.btn_next_context.setIcon(QIcon(':/resources/icon-right-arrow.png'))
            self.btn_prev_context.setFixedSize(25, 25)
            self.btn_next_context.setFixedSize(25, 25)
            self.btn_prev_context.clicked.connect(self.previous_context)
            self.btn_next_context.clicked.connect(self.next_context)

            self.btn_info = QPushButton()
            self.btn_info.setText('i')
            self.btn_info.setFixedSize(25, 25)
            self.btn_info.clicked.connect(self.showContextInfo)

            button_layout.addWidget(self.btn_prev_context)
            button_layout.addWidget(self.btn_next_context)
            button_layout.addWidget(self.btn_info)

            # Add the container to the top bar layout
            self.topbar_layout.addWidget(self.button_container)

            self.button_container.hide()

        def load(self):
            self.group_settings.load()
            self.agent_name_label.setText(self.parent.context.chat_name)
            with block_signals(self.title_label):
                self.title_label.setText(self.parent.context.chat_title)

            member_configs = [member.agent.config for _, member in self.parent.context.members.items()]
            member_avatar_paths = [config.get('general.avatar_path', '') for config in member_configs]

            circular_pixmap = path_to_pixmap(member_avatar_paths, diameter=30)
            self.profile_pic_label.setPixmap(circular_pixmap)

        def title_edited(self, text):
            sql.execute(f"""
                UPDATE contexts
                SET summary = ?
                WHERE id = ?
            """, (text, self.parent.context.id,))
            self.parent.context.chat_title = text

        def showContextInfo(self):
            context_id = self.parent.context.id
            leaf_id = self.parent.context.leaf_id

            display_messagebox(
                icon=QMessageBox.Warning,
                text=f"Context ID: {context_id}\nLeaf ID: {leaf_id}",
                title="Context Info",
                buttons=QMessageBox.Ok
            )

        def previous_context(self):
            context_id = self.parent.context.id
            prev_context_id = sql.get_scalar(
                "SELECT id FROM contexts WHERE id < ? AND parent_id IS NULL ORDER BY id DESC LIMIT 1;", (context_id,))
            if prev_context_id:
                self.parent.goto_context(prev_context_id)
                self.parent.load()
                self.btn_next_context.setEnabled(True)
            else:
                self.btn_prev_context.setEnabled(False)

        def next_context(self):
            context_id = self.parent.context.id
            next_context_id = sql.get_scalar(
                "SELECT id FROM contexts WHERE id > ? AND parent_id IS NULL ORDER BY id LIMIT 1;", (context_id,))
            if next_context_id:
                self.parent.goto_context(next_context_id)
                self.parent.load()
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
            if not self.group_settings.isVisible():
                self.group_settings.show()
                self.group_settings.load()
            else:
                self.group_settings.hide()

    def on_button_click(self):
        if self.context.responding:
            self.context.stop()
            # self.main.send_button.update_icon(is_generating=False)
        else:
            self.send_message(self.main.message_text.toPlainText(), clear_input=True)

    def send_message(self, message, role='user', clear_input=False):
        # check if threadpool is active
        if self.threadpool.activeThreadCount() > 0:
            return

        new_msg = self.context.save_message(role, message)
        self.last_member_msgs = {}

        if not new_msg:
            return

        self.main.send_button.update_icon(is_generating=True)

        if clear_input:
            self.main.message_text.clear()
            self.main.message_text.setFixedHeight(51)
            self.main.send_button.setFixedHeight(51)

        # if role == 'user':
        #     # msg = Message(msg_id=-1, role='user', content=new_msg.content)
        #     self.insert_bubble(new_msg)

        self.context.message_history.load_branches()
        self.refresh()
        QTimer.singleShot(5, self.after_send_message)

    def after_send_message(self):
        self.scroll_to_end()
        runnable = self.RespondingRunnable(self)
        self.threadpool.start(runnable)

    class RespondingRunnable(QRunnable):
        def __init__(self, parent):
            super().__init__()
            self.main = parent.main
            self.page_chat = parent
            self.context = self.page_chat.context

        def run(self):
            # self.context.start()
            try:
                self.context.start()
                self.main.finished_signal.emit()
            except Exception as e:
                self.main.error_occurred.emit(str(e))

    def on_error_occurred(self, error):
        self.last_member_msgs = {}
        self.context.responding = False
        self.main.send_button.update_icon(is_generating=False)
        self.decoupled_scroll = False

        display_messagebox(
            icon=QMessageBox.Critical,
            text=error,
            title="Response Error",
            buttons=QMessageBox.Ok
        )

    def on_receive_finished(self):
        self.last_member_msgs = {}
        self.context.responding = False
        self.main.send_button.update_icon(is_generating=False)
        self.decoupled_scroll = False

        self.refresh()
        self.try_generate_title()

    def try_generate_title(self):
        current_title = self.context.chat_title
        if current_title != '':
            return

        first_config = next(iter(self.context.member_configs.values()))
        auto_title = first_config.get('context.auto_title', True)

        if not auto_title:
            return
        if not self.context.message_history.count(incl_roles=('user',)) == 1:
            return

        title_runnable = self.AutoTitleRunnable(self)
        self.threadpool.start(title_runnable)

    class AutoTitleRunnable(QRunnable):
        def __init__(self, parent):
            super().__init__()
            self.page_chat = parent
            self.context = self.page_chat.context

        def run(self):
            user_msg = self.context.message_history.last(incl_roles=('user',))

            model_name = config.get_value('system.auto_title_model', 'gpt-3.5-turbo')
            model_obj = (model_name, self.context.main.system.models.to_dict()[model_name])  # todo make prettier

            prompt = config.get_value('system.auto_title_prompt',
                                      'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}')
            prompt = prompt.format(user_msg=user_msg['content'])

            try:
                title = llm.get_scalar(prompt, model_obj=model_obj)
                title = title.replace('\n', ' ').strip("'").strip('"')
                self.page_chat.topbar.title_edited(title)
                with block_signals(self.page_chat.topbar.title_label):
                    self.page_chat.topbar.title_label.setText(self.context.chat_title)
            except Exception as e:
                # show error message
                display_messagebox(
                    icon=QMessageBox.Warning,
                    text="Error generating title, try changing the model in settings.\n\n" + str(e),
                    title="Auto-title Error",
                    buttons=QMessageBox.Ok
                )

    def insert_bubble(self, message=None):
        msg_container = self.MessageContainer(self, message=message)

        if message.role == 'assistant':
            member_id = message.member_id
            if member_id:
                self.last_member_msgs[member_id] = msg_container

        index = len(self.chat_bubbles)
        self.chat_bubbles.insert(index, msg_container)
        self.chat_scroll_layout.insertWidget(index, msg_container)

        return msg_container

    def new_sentence(self, member_id, sentence):
        if member_id not in self.last_member_msgs:
            with self.context.message_history.thread_lock:
                # msg_id = self.context.message_history.get_next_msg_id()
                msg = Message(msg_id=-1, role='assistant', content=sentence, member_id=member_id)
                self.insert_bubble(msg)
                self.last_member_msgs[member_id] = self.chat_bubbles[-1]
        else:
            last_member_bubble = self.last_member_msgs[member_id]
            try:  # Safely catch exception if bubble not found (when changing page)
                last_member_bubble.bubble.append_text(sentence)
            except Exception as e:
                print(e)

        if not self.decoupled_scroll:
            QTimer.singleShot(0, self.scroll_to_end)

    def delete_messages_since(self, msg_id):
        # DELETE ALL CHAT BUBBLES >= msg_id
        while self.chat_bubbles:
            cont = self.chat_bubbles.pop()
            bubble = cont.bubble
            self.chat_scroll_layout.removeWidget(cont)
            cont.deleteLater()
            if bubble.msg_id == msg_id:
                break

        # GET INDEX OF MESSAGE IN MESSAGE HISTORY
        index = -1  # todo dirty, change Messages() list
        for i in range(len(self.context.message_history.messages)):
            msg = self.context.message_history.messages[i]
            if msg.id == msg_id:
                index = i
                break

        # DELETE ALL MESSAGES >= msg_id
        if index <= len(self.context.message_history.messages) - 1:
            self.context.message_history.messages[:] = self.context.message_history.messages[:index]

        pass

    def scroll_to_end(self):
        QApplication.processEvents()  # process GUI events to update content size todo?
        scrollbar = self.main.page_chat.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def new_context(self, copy_context_id=None, agent_id=None):
        sql.execute("INSERT INTO contexts (id) VALUES (NULL)")
        context_id = sql.get_scalar("SELECT MAX(id) FROM contexts")
        if copy_context_id:
            copied_cm_id_list = sql.get_results("""
                SELECT
                    cm.id
                FROM contexts_members cm
                WHERE cm.context_id = ?
                    AND cm.del = 0
                ORDER BY cm.id""", (copy_context_id,), return_type='list')

            sql.execute(f"""
                INSERT INTO contexts_members (
                    context_id,
                    agent_id,
                    agent_config,
                    ordr,
                    loc_x,
                    loc_y
                ) 
                SELECT
                    ?,
                    cm.agent_id,
                    cm.agent_config,
                    cm.ordr,
                    cm.loc_x,
                    cm.loc_y
                FROM contexts_members cm
                WHERE cm.context_id = ?
                    AND cm.del = 0
                ORDER BY cm.id""",
                        (context_id, copy_context_id))

            pasted_cm_id_list = sql.get_results("""
                SELECT
                    cm.id
                FROM contexts_members cm
                WHERE cm.context_id = ?
                    AND cm.del = 0
                ORDER BY cm.id""", (context_id,), return_type='list')

            mapped_cm_id_dict = dict(zip(copied_cm_id_list, pasted_cm_id_list))
            # mapped_cm_id_dict[0] = 0

            # Insert into contexts_members_inputs where member_id and input_member_id are switched to the mapped ids
            existing_context_members_inputs = sql.get_results("""
                SELECT cmi.id, cmi.member_id, cmi.input_member_id, cmi.type
                FROM contexts_members_inputs cmi
                LEFT JOIN contexts_members cm
                    ON cm.id=cmi.member_id
                WHERE cm.context_id = ?""",
                                                              (copy_context_id,))

            for cmi in existing_context_members_inputs:
                cmi = list(cmi)
                # cmi[1] = 'NULL' if cmi[1] is None else mapped_cm_id_dict[cmi[1]]
                cmi[1] = mapped_cm_id_dict[cmi[1]]
                cmi[2] = None if cmi[2] is None else mapped_cm_id_dict[cmi[2]]

                sql.execute("""
                    INSERT INTO contexts_members_inputs
                        (member_id, input_member_id, type)
                    VALUES
                        (?, ?, ?)""", (cmi[1], cmi[2], cmi[3]))

        elif agent_id is not None:
            sql.execute("""
                INSERT INTO contexts_members
                    (context_id, agent_id, agent_config)
                SELECT
                    ?, id, config
                FROM agents
                WHERE id = ?""", (context_id, agent_id))

        self.goto_context(context_id)
        self.main.page_chat.load()

    def goto_context(self, context_id=None):
        from agentpilot.context.base import Context
        self.main.page_chat.context = Context(main=self.main, context_id=context_id)

    class MessageContainer(QWidget):
        # Container widget for the profile picture and bubble
        def __init__(self, parent, message):
            super().__init__(parent=parent)
            self.parent = parent
            self.setProperty("class", "message-container")

            self.member_config = parent.context.member_configs.get(message.member_id)
            # self.agent = member.agent if member else None

            self.layout = QHBoxLayout(self)
            self.layout.setSpacing(0)
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.bubble = self.create_bubble(message)

            show_avatar_when = config.get_value('display.agent_avatar_show')
            context_is_multi_member = len(self.parent.context.member_configs) > 1

            show_avatar = (show_avatar_when == 'In Group' and context_is_multi_member) or show_avatar_when == 'Always'

            if show_avatar:
                agent_avatar_path = self.member_config.get('general.avatar_path', '') if self.member_config else ''
                diameter = parent.context.main.system.roles.to_dict().get(message.role, {}).get('display.bubble_image_size', 30)  # todo dirty
                if diameter == '': diameter = 0  # todo hacky
                circular_pixmap = path_to_pixmap(agent_avatar_path, diameter=int(diameter))

                self.profile_pic_label = QLabel(self)
                self.profile_pic_label.setPixmap(circular_pixmap)
                self.profile_pic_label.setFixedSize(40, 30)
                self.profile_pic_label.mousePressEvent = self.view_log

                # add pic label to a qvlayout and add a stretch after it if config.display.bubble_image_position = "Top"
                # create a container widget for the pic and bubble
                image_container = QWidget(self)
                image_container_layout = QVBoxLayout(image_container)
                image_container_layout.setSpacing(0)
                image_container_layout.setContentsMargins(0, 0, 0, 0)
                image_container_layout.addWidget(self.profile_pic_label)
                # self.layout.addWidget(self.profile_pic_label)

                if config.get_value('display.agent_avatar_position') == 'Top':
                    image_container_layout.addStretch(1)

                self.layout.addWidget(image_container)
            self.layout.addWidget(self.bubble)

            self.branch_msg_id = message.id

            if getattr(self.bubble, 'has_branches', False):
                self.branch_msg_id = next(iter(self.bubble.branch_entry.keys()))
                self.bg_bubble = QWidget(self)
                self.bg_bubble.setProperty("class", "bubble-bg")
                user_bubble_bg_color = config.get_value('display.user_bubble_bg_color')
                # set hex to 30% opacity
                user_bubble_bg_color = user_bubble_bg_color.replace('#', '#4d')

                self.bg_bubble.setStyleSheet(f"background-color: {user_bubble_bg_color}; border-top-left-radius: 2px; "
                                             "border-bottom-left-radius: 2px; border-top-right-radius: 6px; "
                                             "border-bottom-right-radius: 6px;")
                self.bg_bubble.setFixedSize(8, self.bubble.size().height() - 2)

                self.layout.addWidget(self.bg_bubble)

            self.btn_resend = self.BubbleButton_Resend(self)
            self.layout.addWidget(self.btn_resend)
            # self.btn_resend.setGeometry(self.calculate_button_position())
            self.btn_resend.hide()

            self.layout.addStretch(1)

            self.log_windows = []

        def create_bubble(self, message):
            page_chat = self.parent

            params = {
                'msg_id': message.id,
                'text': message.content,
                'viewport': page_chat,
                'role': message.role,
                'parent': self,
                'member_id': message.member_id,
            }
            if message.role == 'user':
                bubble = page_chat.MessageBubbleUser(**params)
            elif message.role == 'code':
                bubble = page_chat.MessageBubbleCode(**params)
            else:
                bubble = page_chat.MessageBubbleBase(**params)

            return bubble

        def view_log(self, _):
            msg_id = self.bubble.msg_id
            log = sql.get_scalar("SELECT log FROM contexts_messages WHERE id = ?;", (msg_id,))
            if not log or log == '':
                return

            json_obj = json.loads(log)
            # Convert JSON data to a pretty string
            pretty_json = json.dumps(json_obj, indent=4)

            # Create new window
            log_window = QMainWindow()
            log_window.setWindowTitle('Message Input')

            # Create QTextEdit widget to show JSON data
            text_edit = QTextEdit()

            # Set JSON data to the text edit
            text_edit.setText(pretty_json)

            # Set QTextEdit as the central widget of the window
            log_window.setCentralWidget(text_edit)

            # Show the new window
            log_window.show()
            self.log_windows.append(log_window)

        class BubbleButton_Resend(QPushButton):
            def __init__(self, parent=None):
                super().__init__(parent=parent)
                self.setProperty("class", "resend")
                self.parent = parent
                self.clicked.connect(self.resend_msg)

                self.setFixedSize(32, 24)

                icon = QIcon(QPixmap(":/resources/icon-send.png"))
                self.setIcon(icon)

            def resend_msg(self):
                branch_msg_id = self.parent.branch_msg_id
                editing_msg_id = self.parent.bubble.msg_id

                # Deactivate all other branches
                self.parent.parent.context.deactivate_all_branches_with_msg(editing_msg_id)

                # Get user message
                msg_to_send = self.parent.bubble.toPlainText()

                # Delete all messages from editing bubble onwards
                self.parent.parent.delete_messages_since(editing_msg_id)

                # Create a new leaf context CHECK
                sql.execute(
                    "INSERT INTO contexts (parent_id, branch_msg_id) SELECT context_id, id FROM contexts_messages WHERE id = ?",
                    (branch_msg_id,))
                new_leaf_id = sql.get_scalar('SELECT MAX(id) FROM contexts')
                # self.parent.parent.refresh()
                self.parent.parent.context.leaf_id = new_leaf_id

                # Finally send the message like normal
                self.parent.parent.send_message(msg_to_send, clear_input=False)
                # self.parent.parent.context.message_history.load()

                # #####
                # return
                #
                # branch_msg_id = self.parent.branch_msg_id
                #
                # # ######
                # # bmi_role = sql.get_scalar("SELECT role FROM contexts_messages WHERE id = ?;", (branch_msg_id,))
                # # if bmi_role != 'user':
                # #     pass
                # # ######
                #
                # # page_chat = self.parent.parent
                # self.parent.parent.context.deactivate_all_branches_with_msg(self.parent.bubble.msg_id)
                # sql.execute(
                #     "INSERT INTO contexts (parent_id, branch_msg_id) SELECT context_id, id FROM contexts_messages WHERE id = ?",
                #     (branch_msg_id,))
                # new_leaf_id = sql.get_scalar('SELECT MAX(id) FROM contexts')
                # self.parent.parent.context.leaf_id = new_leaf_id
                #
                # # print(f"LEAF ID SET TO {new_leaf_id} BY bubble.resend_msg")
                # # if new_leaf_id != self.parent.parent.context.leaf_id:
                # #     print('LEAF ID NOT SET CORRECTLY')
                # # self.parent.parent.context.load_branches()
                #
                # msg_to_send = self.parent.bubble.toPlainText()
                # self.parent.parent.delete_messages_since(self.parent.bubble.msg_id)
                #
                # # Finally send the message like normal
                # self.parent.parent.send_message(msg_to_send, clear_input=False)
                #
                # # page_chat.context.message_history.load_messages()
                # # refresh the gui to process events
                # # QApplication.processEvents()
                #
                # # print current leaf id
                # # print('LEAF ID: ', self.parent.parent.context.leaf_id)
                # # self.parent.parent.context.refresh()

            def check_and_toggle(self):
                if self.parent.bubble.toPlainText() != self.parent.bubble.original_text:
                    self.show()
                else:
                    self.hide()

    class MessageBubbleBase(QTextEdit):
        def __init__(self, msg_id, text, viewport, role, parent, member_id=None):
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
            self.member_id = member_id

            self.agent_config = parent.member_config if parent.member_config else {}  # todo - remove?
            self.role = role
            self.setProperty("class", "bubble")
            self.setProperty("class", role)
            self._viewport = viewport
            self.margin = QMargins(6, 0, 6, 0)
            self.text = ''
            self.original_text = text
            self.enable_markdown = self.agent_config.get('context.display_markdown', True)
            if self.role == 'code':
                self.enable_markdown = False

            self.setWordWrapMode(QTextOption.WordWrap)
            # self.highlighter = PythonHighlighter(self.document())
            # text_font = config.get_value('display.text_font')
            # size_font = self.parent.temp_text_size if self.parent.temp_text_size else config.get_value('display.text_size')
            # self.font = QFont()  # text_font, size_font)
            # if text_font != '': self.font.setFamily(text_font)
            # self.font.setPointSize(size_font)
            # self.setCurrentFont(self.font)
            # self.setFontPointSize(20)

            self.append_text(text)

        def setMarkdownText(self, text):
            global PRIMARY_COLOR, TEXT_COLOR
            font = config.get_value('display.text_font')
            size = config.get_value('display.text_size')

            if getattr(self, 'role', '') == 'user':
                color = config.get_value('display.user_bubble_text_color')
            else:
                color = config.get_value('display.assistant_bubble_text_color')

            css_background = f"code {{ color: #919191; }}"
            css_font = f"body {{ color: {color}; font-family: {font}; font-size: {size}px; }}"
            css = f"{css_background}\n{css_font}"

            if self.enable_markdown:
                text = mistune.markdown(text)
            else:
                text = text.replace('\n', '<br>')
                text = text.replace('\t', '&nbsp;&nbsp;&nbsp;&nbsp;')

            html = f"<style>{css}</style><body>{text}</body>"

            # Set HTML to QTextEdit
            self.setHtml(html)

        def calculate_button_position(self):
            button_width = 32
            button_height = 32
            button_x = self.width() - button_width
            button_y = self.height() - button_height
            return QRect(button_x, button_y, button_width, button_height)

        def append_text(self, text):
            cursor = self.textCursor()

            start = cursor.selectionStart()
            end = cursor.selectionEnd()

            self.text += text
            self.original_text = self.text
            self.setMarkdownText(self.text)
            self.update_size()

            cursor.setPosition(start, cursor.MoveAnchor)
            cursor.setPosition(end, cursor.KeepAnchor)

            self.setTextCursor(cursor)

        def sizeHint(self):
            lr = self.margin.left() + self.margin.right()
            tb = self.margin.top() + self.margin.bottom()
            doc = self.document().clone()
            doc.setTextWidth((self._viewport.width() - lr) * 0.8)
            width = min(int(doc.idealWidth()), 520)
            return QSize(width + lr, int(doc.size().height() + tb))

        def update_size(self):
            size_hint = self.sizeHint()
            self.setFixedSize(size_hint.width(), size_hint.height())
            if hasattr(self.parent, 'bg_bubble'):
                self.parent.bg_bubble.setFixedSize(8, self.parent.bubble.size().height() - 2)
            self.updateGeometry()
            self.parent.updateGeometry()

        def minimumSizeHint(self):
            return self.sizeHint()

        def keyPressEvent(self, event):
            super().keyPressEvent(event)

    class MessageBubbleUser(MessageBubbleBase):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # self.parent.parent.context.message_history.load_branches()
            branches = self.parent.parent.context.message_history.branches
            self.branch_entry = {k: v for k, v in branches.items() if self.msg_id == k or self.msg_id in v}
            self.has_branches = len(self.branch_entry) > 0

            if self.has_branches:
                self.branch_buttons = self.BubbleBranchButtons(self.branch_entry, parent=self)
                self.branch_buttons.hide()

            self.textChanged.connect(self.text_editted)

        def enterEvent(self, event):
            super().enterEvent(event)
            if self.has_branches:
                self.branch_buttons.reposition()
                self.branch_buttons.show()

        def leaveEvent(self, event):
            super().leaveEvent(event)
            if self.has_branches:
                self.branch_buttons.hide()

        def text_editted(self):
            self.text = self.toPlainText()
            self.update_size()

        def keyPressEvent(self, event):
            super().keyPressEvent(event)
            self.parent.btn_resend.check_and_toggle()

        class BubbleBranchButtons(QWidget):
            def __init__(self, branch_entry, parent=None):
                super().__init__(parent=parent)
                self.setProperty("class", "branch-buttons")
                self.parent = parent
                message_bubble = self.parent
                message_container = message_bubble.parent
                self.bubble_id = message_bubble.msg_id
                self.page_chat = message_container.parent

                self.btn_back = QPushButton("🠈", self)
                self.btn_next = QPushButton("🠊", self)
                self.btn_back.setFixedSize(30, 12)
                self.btn_next.setFixedSize(30, 12)

                self.btn_back.setStyleSheet(
                    "QPushButton { background-color: none; } QPushButton:hover { background-color: #555555;}")
                self.btn_next.setStyleSheet(
                    "QPushButton { background-color: none; } QPushButton:hover { background-color: #555555;}")

                self.reposition()

                self.branch_entry = branch_entry
                branch_root_msg_id = next(iter(branch_entry))
                self.child_branches = self.branch_entry[branch_root_msg_id]

                if self.parent.msg_id == branch_root_msg_id:
                    self.btn_back.hide()
                    self.btn_back.setEnabled(False)
                else:
                    indx = branch_entry[branch_root_msg_id].index(self.parent.msg_id)
                    if indx == len(branch_entry[branch_root_msg_id]) - 1:
                        self.btn_next.hide()
                        self.btn_next.setEnabled(False)

                self.btn_back.clicked.connect(self.back)
                self.btn_next.clicked.connect(self.next)

            def reposition(self):
                bubble_width = self.parent.size().width()

                available_width = bubble_width - 8
                half_av_width = available_width / 2

                self.btn_back.setFixedWidth(half_av_width)
                self.btn_next.setFixedWidth(half_av_width)

                self.btn_back.move(4, 0)
                self.btn_next.move(half_av_width + 4, 0)

            def back(self):
                if self.bubble_id in self.branch_entry:
                    return
                else:
                    self.page_chat.context.deactivate_all_branches_with_msg(self.bubble_id)
                    current_index = self.child_branches.index(self.bubble_id)
                    if current_index == 0:
                        self.reload_following_bubbles()
                        return
                    next_msg_id = self.child_branches[current_index - 1]
                    self.page_chat.context.activate_branch_with_msg(next_msg_id)

                self.reload_following_bubbles()

            def next(self):
                if self.bubble_id in self.branch_entry:
                    activate_msg_id = self.child_branches[0]
                    self.page_chat.context.activate_branch_with_msg(activate_msg_id)
                else:
                    current_index = self.child_branches.index(self.bubble_id)
                    if current_index == len(self.child_branches) - 1:
                        return
                    self.page_chat.context.deactivate_all_branches_with_msg(self.bubble_id)
                    next_msg_id = self.child_branches[current_index + 1]
                    self.page_chat.context.activate_branch_with_msg(next_msg_id)

                self.reload_following_bubbles()

            def reload_following_bubbles(self):
                self.page_chat.delete_messages_since(self.bubble_id)
                self.page_chat.context.message_history.load()
                self.page_chat.refresh()
                # self.doarefresh()
                # # doarefresh in a singleshot
                # QTimer.singleShot(1, self.page_chat.context.message_history.load_branches)
                # QTimer.singleShot(1, self.page_chat.context.message_history.load)
                # QTimer.singleShot(2, self.page_chat.refresh)

                # self.page_chat.context.message_history.load_messages()
                # self.page_chat.load()

            # def doarefresh(self):
            #     self.page_chat.refresh()
            #     print('LEAF ID: ', self.page_chat.context.leaf_id)

            def update_buttons(self):
                pass

    class MessageBubbleCode(MessageBubbleBase):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # def __init__(self, msg_id, text, viewport, role, parent):
            #     super().__init__(msg_id, '', viewport, role, parent)

            self.lang, self.code = self.split_lang_and_code(kwargs.get('text', ''))
            self.original_text = self.code
            # self.append_text(self.code)
            self.setToolTip(f'{self.lang} code')
            # self.tag = lang
            self.btn_rerun = self.BubbleButton_Rerun_Code(self)
            self.btn_rerun.setGeometry(self.calculate_button_position())
            self.btn_rerun.hide()

        def start_timer(self):
            self.countdown_stopped = False
            self.countdown = int(self.agent_config.get('actions.code_auto_run_seconds', 5))  #
            self.countdown_button = self.CountdownButton(self)
            self.countdown_button.move(self.btn_rerun.x() - 20, self.btn_rerun.y() + 4)

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
            self.countdown = int(
                self.agent_config.get('actions.code_auto_run_seconds', 5))  # 5  # Reset countdown to 5 seconds
            self.countdown_button.setText(f"{self.countdown}")

            if not self.underMouse():
                self.timer.start()  # Restart the timer

        def check_and_toggle_rerun_button(self):
            if self.underMouse():
                self.btn_rerun.show()
            else:
                self.btn_rerun.hide()

        def run_bubble_code(self):
            from agentpilot.plugins.openinterpreter.src.core.core import Interpreter
            member_id = self.member_id
            member = self.parent.parent.context.members[member_id]
            agent = member.agent
            agent_object = getattr(agent, 'agent_object', None)

            if agent_object:
                run_code_func = getattr(agent_object, 'run_code', None)
            else:
                agent_object = Interpreter()
                run_code_func = agent_object.run_code

            output = run_code_func(self.lang, self.code)

            last_msg = self.parent.parent.context.message_history.last(incl_roles=('user', 'assistant', 'code'))
            if last_msg['id'] == self.msg_id:
                self.parent.parent.send_message(output, role='output')

        class BubbleButton_Rerun_Code(QPushButton):
            def __init__(self, parent=None):
                super().__init__(parent=parent)
                self.bubble = parent
                self.setProperty("class", "rerun")
                self.clicked.connect(self.rerun_code)

                icon = QIcon(QPixmap(":/resources/icon-run.png"))
                self.setIcon(icon)

            def rerun_code(self):
                self.bubble.run_bubble_code()
                # stop timer
                self.bubble.timer.stop()
                self.bubble.countdown_button.hide()
                self.bubble.countdown_stopped = True

        class CountdownButton(QPushButton):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.setText(str(parent.agent_config.get('actions.code_auto_run_seconds', 5)))  # )
                self.setIcon(QIcon())  # Initially, set an empty icon
                self.setStyleSheet("color: white; background-color: transparent;")
                self.setFixedHeight(22)
                self.setFixedWidth(22)

            def enterEvent(self, event):
                icon = QIcon(QPixmap(":/resources/close.png"))
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

            current_pin_state = PIN_STATE
            PIN_STATE = True
            # Show the context menu at current mouse position
            menu.exec_(event.globalPos())
            PIN_STATE = current_pin_state


class SideBar(QWidget):
    def __init__(self, main):
        super().__init__(parent=main)
        self.main = main
        self.setObjectName("SideBarWidget")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setProperty("class", "sidebar")

        self.btn_new_context = self.SideBar_NewContext(self)
        self.btn_settings = self.SideBar_Settings(self)
        self.btn_agents = self.SideBar_Agents(self)
        self.btn_contexts = self.SideBar_Contexts(self)
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Create a button group and add buttons to it
        self.button_group = QButtonGroup(self)
        self.button_group.addButton(self.btn_new_context, 0)
        self.button_group.addButton(self.btn_settings, 1)
        self.button_group.addButton(self.btn_agents, 2)
        self.button_group.addButton(self.btn_contexts, 3)  # 1

        self.title_bar = TitleButtonBar(self)
        self.layout.addWidget(self.title_bar)
        self.layout.addStretch(1)

        self.layout.addWidget(self.btn_settings)
        self.layout.addWidget(self.btn_agents)
        self.layout.addWidget(self.btn_contexts)
        self.layout.addWidget(self.btn_new_context)

    def update_buttons(self):
        is_current_chat = self.main.content.currentWidget() == self.main.page_chat
        icon_iden = 'chat' if not is_current_chat else 'new-large'
        icon = QIcon(QPixmap(f":/resources/icon-{icon_iden}.png"))
        self.btn_new_context.setIcon(icon)

    class SideBar_NewContext(QPushButton):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.main = parent.main
            self.clicked.connect(self.new_context)
            self.icon = QIcon(QPixmap(":/resources/icon-new-large.png"))
            self.setIcon(self.icon)
            self.setToolTip("New context")
            self.setFixedSize(50, 50)
            self.setIconSize(QSize(50, 50))
            self.setCheckable(True)
            self.setObjectName("homebutton")

        def new_context(self):
            is_current_widget = self.main.content.currentWidget() == self.main.page_chat
            if is_current_widget:
                copy_context_id = self.main.page_chat.context.id
                self.main.page_chat.new_context(copy_context_id=copy_context_id)
            else:
                self.load_chat()

        def load_chat(self):
            self.main.content.setCurrentWidget(self.main.page_chat)

    class SideBar_Settings(QPushButton):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.main = parent.main
            self.clicked.connect(self.open_settins)
            self.icon = QIcon(QPixmap(":/resources/icon-settings.png"))
            self.setIcon(self.icon)
            self.setToolTip("Settings")
            self.setFixedSize(50, 50)
            self.setIconSize(QSize(50, 50))
            self.setCheckable(True)

        def open_settins(self):
            self.main.content.setCurrentWidget(self.main.page_settings)

    class SideBar_Agents(QPushButton):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.main = parent.main
            self.clicked.connect(self.open_settins)
            self.icon = QIcon(QPixmap(":/resources/icon-agent.png"))
            self.setIcon(self.icon)
            self.setToolTip("Agents")
            self.setFixedSize(50, 50)
            self.setIconSize(QSize(50, 50))
            self.setCheckable(True)

        def open_settins(self):
            self.main.content.setCurrentWidget(self.main.page_agents)

    class SideBar_Contexts(QPushButton):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.main = parent.main
            self.clicked.connect(self.open_contexts)
            self.icon = QIcon(QPixmap(":/resources/icon-contexts.png"))
            self.setIcon(self.icon)
            self.setToolTip("Contexts")
            self.setFixedSize(50, 50)
            self.setIconSize(QSize(50, 50))
            self.setCheckable(True)

        def open_contexts(self):
            self.main.content.setCurrentWidget(self.main.page_contexts)


class MessageText(QTextEdit):
    enterPressed = Signal()

    def __init__(self, main=None):
        super().__init__(parent=None)
        self.parent = main
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
            cursor.movePosition(QTextCursor.PreviousBlock, QTextCursor.MoveAnchor,
                                1)  # Move cursor inside the code block
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

                # If context not responding
                if not self.parent.page_chat.context.responding:
                    return self.enterPressed.emit()

        se = super().keyPressEvent(event)
        self.setFixedSize(self.sizeHint())
        self.parent.sync_send_button_size()
        return se

    def sizeHint(self):
        doc = QTextDocument()
        doc.setDefaultFont(self.font)
        doc.setPlainText(self.toPlainText())

        min_height_lines = 2

        # Calculate the required width and height
        text_rect = doc.documentLayout().documentSize()
        width = self.width()
        font_height = QFontMetrics(self.font).height()
        num_lines = max(min_height_lines, text_rect.height() / font_height)

        # Calculate height with a maximum
        height = min(338, int(font_height * num_lines))

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

    # def enterEvent(self, event):
    #     self.setStyleSheet("QTextEdit { background-color: rgba(255, 255, 255, 100); }")  # Set opacity back to normal when mouse leaves
    #
    # def leaveEvent(self, event):
    #     self.setStyleSheet("QTextEdit { background-color: rgba(255, 255, 255, 30); }")  # Set opacity back to normal when mouse leaves

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
        self.setFixedSize(70, 46)
        self.setProperty("class", "send")
        self.update_icon(is_generating=False)

    def update_icon(self, is_generating):
        icon_iden = 'send' if not is_generating else 'stop'
        icon = QIcon(QPixmap(f":/resources/icon-{icon_iden}.png"))
        self.setIcon(icon)

    def minimumSizeHint(self):
        return self.sizeHint()

    def sizeHint(self):
        height = self._parent.message_text.height()
        width = 70
        return QSize(width, height)


class Main(QMainWindow):
    new_bubble_signal = Signal(dict)
    new_sentence_signal = Signal(int, str)
    finished_signal = Signal()
    error_occurred = Signal(str)

    mouseEntered = Signal()
    mouseLeft = Signal()

    def check_db(self):
        # Check if the database is available
        try:
            upgrade_db = sql.check_database_upgrade()
            if upgrade_db:
                # ask confirmation first
                if QMessageBox.question(None, "Database outdated",
                                        "Do you want to upgrade the database to the newer version?",
                                        QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                    # exit the app
                    sys.exit(0)
                # get current db version
                db_version = upgrade_db
                # run db upgrade
                while db_version != versions[-1]:  # while not the latest version
                    db_version = upgrade_script.upgrade(db_version)

        except Exception as e:
            if hasattr(e, 'message'):
                if e.message == 'NO_DB':
                    QMessageBox.critical(None, "Error",
                                         "No database found. Please make sure `data.db` is located in the same directory as this executable.")
                elif e.message == 'OUTDATED_APP':
                    QMessageBox.critical(None, "Error",
                                         "The database originates from a newer version of Agent Pilot. Please download the latest version from github.")
                elif e.message == 'OUTDATED_DB':
                    QMessageBox.critical(None, "Error",
                                         "The database is outdated. Please download the latest version from github.")
            sys.exit(0)

    def set_stylesheet(self):
        QApplication.instance().setStyleSheet(get_stylesheet())

    def __init__(self):  # , base_agent=None):
        super().__init__()

        screenrect = QApplication.primaryScreen().availableGeometry()
        self.move(screenrect.right() - self.width(), screenrect.bottom() - self.height())

        # Check if the database is ok
        self.check_db()

        api.load_api_keys()

        self.system = SystemManager()

        self.leave_timer = QTimer(self)
        self.leave_timer.setSingleShot(True)
        self.leave_timer.timeout.connect(self.collapse)

        self.setWindowTitle('AgentPilot')
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setWindowIcon(QIcon(':/resources/icon.png'))
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

        # Horizontal layout for content and sidebar
        hlayout = QHBoxLayout()
        hlayout.addWidget(self.content)
        hlayout.addWidget(self.sidebar)
        hlayout.setSpacing(0)

        self.content_container = QWidget()
        self.content_container.setLayout(hlayout)

        # Adding the scroll area to the main layout
        self._layout.addWidget(self.content_container)

        # Message text and send button
        self.message_text = MessageText(main=self)
        self.message_text.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.message_text.setFixedHeight(46)
        self.message_text.setProperty("class", "msgbox")
        self.send_button = SendButton('', self.message_text, self)

        # Horizontal layout for message text and send button
        self.hlayout = QHBoxLayout()
        self.hlayout.addWidget(self.message_text)
        self.hlayout.addWidget(self.send_button)
        self.hlayout.setSpacing(0)

        # Vertical layout for button bar and input layout
        input_layout = QVBoxLayout()
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
        self.finished_signal.connect(self.page_chat.on_receive_finished)
        self.error_occurred.connect(self.page_chat.on_error_occurred)
        self.oldPosition = None
        self.expanded = False

        self.show()
        self.page_chat.load()
        self.page_settings.page_system.refresh_dev_mode()

    def sync_send_button_size(self):
        self.send_button.setFixedHeight(self.message_text.height())

    def is_bottom_corner(self):
        screen_geo = QGuiApplication.primaryScreen().geometry()  # get screen geometry
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
        try:
            app = QApplication(sys.argv)
            app.setStyleSheet(get_stylesheet())
            m = Main()  # self.agent)
            m.expand()
            app.exec()
        except Exception as e:
            if 'OPENAI_API_KEY' in os.environ:
                # When debugging in IDE, re-raise
                raise e
            display_messagebox(
                icon=QMessageBox.Critical,
                title='Error',
                text=str(e)
            )
