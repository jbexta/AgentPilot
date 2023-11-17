import json
import sys
from threading import Thread
from contextlib import contextmanager
from functools import partial

from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtWidgets import *
from PySide6.QtCore import QThreadPool, Signal, QSize, QEvent, QTimer, QMargins, QRect, QRunnable, Slot, QMimeData, \
    QPoint, QObject, QRectF, QLineF, QPointF
from PySide6.QtGui import QPixmap, QPalette, QColor, QIcon, QFont, QPainter, QPainterPath, QTextCursor, QIntValidator, \
    QTextOption, QTextDocument, QFontMetrics, QGuiApplication, Qt, QCursor, QFontDatabase, QBrush, QMouseEvent, \
    QTransform, QPen, QWheelEvent, QKeyEvent

from agentpilot.utils.filesystem import simplify_path, unsimplify_path
from agentpilot.utils.helpers import create_circular_pixmap
from agentpilot.utils import sql, api, config, resources_rc

import mistune

from context.base import Message


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


DEV_API_KEY = None
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
QComboBox {{
    color: {TEXT_COLOR};
}}
QScrollBar {{
    width: 0px;
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
        palette.setColor(QPalette.Highlight, '#0dffffff')  # Setting it to red
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


class CComboBox(QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        global PIN_STATE
        self.current_pin_state = PIN_STATE

        self.setFixedWidth(150)

    def showPopup(self):
        global PIN_STATE
        self.current_pin_state = PIN_STATE
        PIN_STATE = True
        super().showPopup()

    def hidePopup(self):
        global PIN_STATE
        super().hidePopup()
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

        self.setPos(-42, 100)

        pixmap = QPixmap(":/resources/icon-agent.png")
        self.setBrush(QBrush(pixmap.scaled(50, 50)))

        # set border color
        self.setPen(QPen(QColor(BORDER_COLOR), 2))

        # image_with_opacity = QPixmap(pixmap.size())
        # image_with_opacity.fill(Qt.transparent)
        #
        # painter = QPainter(image_with_opacity)
        # painter.setOpacity(opacity)
        # painter.drawPixmap(0, 0, pixmap)
        # painter.end()
        # self.setBrush(QBrush(image_with_opacity.scaled(50, 50)))

        self.output_point = ConnectionPoint(self, False)
        self.output_point.setPos(self.rect().width() - 4, self.rect().height() / 2)

        self.setAcceptHoverEvents(True)

    # def mouseMoveEvent(self, event):
    #     if self.output_point.contains(event.pos() - self.output_point.pos()):
    #         return

        # if self.parent.new_line:
        #     return
        #
        # super(DraggableAgent, self).mouseMoveEvent(event)
        #
        # for line in self.parent.lines.values():
        #     line.updatePosition()

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
        self.id = id
        self.parent = parent
        # self.member_inputs = [int(x) for x in member_inp_str.split(',')] if member_inp_str else []
        # self.member_inputs is a zipped dict of {member_inp: member_type}, split both by comma

        if member_type_str:
            member_inp_str = '0' if member_inp_str == 'NULL' else member_inp_str  # todo dirty
        self.member_inputs = dict(zip([int(x) for x in member_inp_str.split(',')], member_type_str.split(','))) if member_type_str else {}

        self.setPos(x, y)

        agent_config = json.loads(agent_config)
        hide_responses = agent_config.get('group.hide_responses', False)
        agent_avatar_path = agent_config.get('general.avatar_path', '')
        agent_avatar_path = unsimplify_path(agent_avatar_path)

        pixmap = QPixmap(agent_avatar_path)

        opacity = 0.2 if hide_responses else 1
        image_with_opacity = QPixmap(pixmap.size())
        image_with_opacity.fill(Qt.transparent)

        painter = QPainter(image_with_opacity)
        painter.setOpacity(opacity)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()

        self.setBrush(QBrush(image_with_opacity.scaled(50, 50)))

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
        self.close_btn.move(pos.x() + self.rect().width() + 40, pos.y() + 30)
        self.close_btn.show()
        self.hide_btn.move(pos.x() + self.rect().width() + 40, pos.y() + 75)
        self.hide_btn.show()
        super(DraggableAgent, self).hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.output_point.setHighlighted(False)
        if not self.isUnderMouse():
            self.close_btn.hide()
            self.hide_btn.hide()
        super(DraggableAgent, self).hoverLeaveEvent(event)

    # def mousePressEvent(self, event):
    #     # if self.output_point.contains(event.pos() - self.output_point.pos()):
    #     #     self.parent.new_line = TemporaryConnectionLine(self.output_point)
    #     #     self.parent.scene.addItem(self.parent.new_line)
    #     # elif self.input_point.contains(event.pos() - self.input_point.pos()):
    #     #     if self.parent.new_line:
    #     #         print('finish line')
    #     # else:
    #     super(DraggableAgent, self).mousePressEvent(event)

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

        # on hover mouse leave
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
            # set color = red
            self.setStyleSheet("background-color: transparent; color: darkred;")
            # self.move(self.x() + self.rect().width() + 10, self.y() + 10)
            self.hide()

            # on mouse clicked
            self.clicked.connect(self.hide_agent)

        # on hover mouse leave
        def leaveEvent(self, event):
            # # if mouse isnt over close_btn
            #
            # if
            #     self.parent.close_btn.hide()
            # if not self.parent.hide_btn.isUnderMouse():
            #     self.parent.hide_btn.hide()
            super().leaveEvent(event)

        def hide_agent(self):
            self.parent.parent.select_ids([self.id])
            qcheckbox = self.parent.parent.agent_settings.page_group.hide_responses
            qcheckbox.setChecked(not qcheckbox.isChecked())
            # reload the agents
            self.parent.parent.load()
            #= not self.parent.parent.agent_settings.page_group.hide_responses


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
        ctrl_point2 = end_point.scenePos() + QPointF(50, 0)    # Control point 2 left of end
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
        # painter.setPen(QPen(self.color, line_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
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
        agent_avatar_path = agent_conf.get('general.avatar_path', '')  # /home/jb/Desktop/AgentPilot-0.0.9_Portable_Linux_x86_64/avatars/snoop.png
        unsimp_path = unsimplify_path(agent_avatar_path)
        self.setBrush(QBrush(QPixmap(unsimp_path).scaled(50, 50)))
        self.setCentredPos(pos)


    def setCentredPos(self, pos):
        self.setPos(pos.x() - self.rect().width() / 2, pos.y() - self.rect().height() / 2)

    # when the mouse moves it updates the position
    # def hoverMoveEvent(self, event):
    #     super(TemporaryInsertableAgent, self).hoverMoveEvent(event)
    #     # self.parent.update()
    #     print('ss)')


class ConnectionPoint(QGraphicsEllipseItem):
    def __init__(self, parent, is_input):
        radius = 2
        super(ConnectionPoint, self).__init__(0, 0, 2 * radius, 2 * radius, parent)
        self.is_input = is_input
        self.setBrush(QBrush(Qt.darkGray if is_input else Qt.darkRed))
        self.connections = []

    def setHighlighted(self, highlighted):
        if highlighted:
            self.setBrush(QBrush(Qt.red))  # Change this to your desired highlight color
        else:
            self.setBrush(QBrush(Qt.black))  # Change this to your original color

    def contains(self, point):
        distance = (point - self.rect().center()).manhattanLength()
        return distance <= 12


class CustomGraphicsView(QGraphicsView):
    def __init__(self, scene, parent):
        super(CustomGraphicsView, self).__init__(scene, parent)
        self.setMouseTracking(True)
        # self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.parent = parent

    def enterEvent(self, event):
        print("Mouse entered the view")
        # You can emit a signal here if you want to notify other parts of your application
        super(CustomGraphicsView, self).enterEvent(event)

    def leaveEvent(self, event):
        print("Mouse left the view")
        # You can emit a signal here if you want to notify other parts of your application
        super(CustomGraphicsView, self).leaveEvent(event)

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
                    new_pen = QPen(QColor(255, 0, 0, 255), old_pen.width())  # Create a new pen with 30% opacity red color
                    item.setPen(new_pen)

                self.parent.scene.update()

                # ask for confirmation
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Warning)
                msg.setText("Are you sure you want to delete the selected items?")
                msg.setWindowTitle("Delete Items")
                msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
                retval = msg.exec_()
                if retval == QMessageBox.Ok:
                    # delete all inputs from context
                    context_id = self.parent.parent.parent.context.id
                    for member_id, inp_member_id in del_input_ids:
                        # inp_member_id = 'NULL' if inp_member_id == 0 else inp_member_id
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
                            DELETE FROM contexts_members 
                            WHERE context_id = ?
                                AND id = ?""", (context_id, agent_id,))
                    self.parent.load()
                else:
                    for item in all_del_objects:
                        item.setBrush(all_del_objects_old_brushes.pop(0))
                        item.setPen(all_del_objects_old_pens.pop(0))
                    # self.parent.scene.update()

        else:
            super(CustomGraphicsView, self).keyPressEvent(event)

    def mousePressEvent(self, event):
        if self.parent.new_agent:
            self.parent.add_member()
        else:
            mouse_scene_position = self.mapToScene(event.pos())
            for agent_id, agent in self.parent.members.items():
                if isinstance(agent, DraggableAgent):
                    # event_pos = event.pos()
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
                # self.update()
        super(CustomGraphicsView, self).mousePressEvent(event)


class GroupTopBar(QWidget):
    def __init__(self, parent):
        super(GroupTopBar, self).__init__(parent)
        self.parent = parent

        self.layout = QHBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.btn_choose_member = QPushButton('Add Member', self)
        self.btn_choose_member.clicked.connect(self.choose_member)
        self.btn_choose_member.setFixedWidth(115)
        self.layout.addWidget(self.btn_choose_member)

        # add spacer
        spacer = QSpacerItem(20, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.layout.addItem(spacer)

        # dropdown box which has the items "Sequential", "Random", and "Realistic"
        self.group_mode_combo_box = QComboBox(self)
        self.group_mode_combo_box.addItem("Sequential")
        self.group_mode_combo_box.addItem("Random")
        self.group_mode_combo_box.addItem("Realistic")
        self.group_mode_combo_box.setFixedWidth(115)
        self.layout.addWidget(self.group_mode_combo_box)

        # add spacer
        spacer = QSpacerItem(20, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.layout.addItem(spacer)

        # label "Input type:"
        self.input_type_label = QLabel("Input type:", self)
        self.layout.addWidget(self.input_type_label)

        # dropdown box which has the label "Input type:" and the items "Message", "Context"
        self.input_type_combo_box = QComboBox(self)
        self.input_type_combo_box.addItem("Message")
        self.input_type_combo_box.addItem("Context")
        self.input_type_combo_box.setFixedWidth(115)
        self.layout.addWidget(self.input_type_combo_box)
        # on input_type changed
        self.input_type_combo_box.currentIndexChanged.connect(self.input_type_changed)


        self.layout.addStretch(1)

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
                name,
                '' AS chat_button,
                '' AS del_button
            FROM agents
            ORDER BY id DESC""")
        for row_data in data:
            id, avatar, conf, name, chat_button, del_button = row_data
            conf = json.loads(conf)
            icon = QIcon(QPixmap(conf.get('general.avatar_path', '')))  # Replace with your image path
            item = QListWidgetItem()
            item.setIcon(icon)
            item.setText(name)
            item.setData(Qt.UserRole, (id, conf))

            # set image
            listWidget.addItem(item)

        listWidget.itemDoubleClicked.connect(self.parent.insertAgent)

        self.dlg.exec_()

    class CustomQDialog(QDialog):
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
        # line_inp_member_id = 'NULL' if line_inp_member_id == 0 else line_inp_member_id

        # update db
        # 0 = message, 1 = context
        sql.execute("""
            UPDATE contexts_members_inputs
            SET type = ?
            WHERE member_id = ?
                AND COALESCE(input_member_id, 0) = ?""",
            (index, line_member_id, line_inp_member_id))

        self.parent.load()


class GroupSettings(QWidget):
    def __init__(self, parent):
        super(GroupSettings, self).__init__(parent)
        # self.context = self.parent.parent.context

        self.parent = parent
        layout = QVBoxLayout(self)

        self.group_topbar = GroupTopBar(self)
        layout.addWidget(self.group_topbar)

        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, 500, 250)
        self.scene.selectionChanged.connect(self.on_selection_changed)

        self.view = CustomGraphicsView(self.scene, self)

        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        layout.addWidget(self.view)

        self.user_bubble = FixedUserBubble(self)
        self.scene.addItem(self.user_bubble)

        self.members = {}  # id: member
        self.lines = {}  # (member_id, inp_member_id): line

        self.new_line = None
        self.new_agent = None

        self.agent_settings = AgentSettings(self, is_context_member_agent=True)
        self.agent_settings.hide()
        layout.addWidget(self.agent_settings)

    def load(self):
        self.load_members()
        self.load_member_inputs()

    def load_members(self):
        # Clear any existing members from the scene
        for m_id, member in self.members.items():
            # destroy member.close_btn
            member.close_btn.setParent(None)
            member.close_btn.deleteLater()
            # destroy member.hide_btn
            member.hide_btn.setParent(None)
            member.hide_btn.deleteLater()
            self.scene.removeItem(member)
        self.members = {}

        # Fetch member records from the database
        # query = """
        #     SELECT
        #         cm.id,
        #         cm.agent_id,
        #         cm.agent_config,
        #         cm.loc_x,
        #         cm.loc_y,
        #         CASE WHEN cmi.input_member_id IS NULL THEN NULL ELSE GROUP_CONCAT(cmi.input_member_id) END as input_members,
        #         CASE WHEN cmi.type IS NULL THEN NULL ELSE GROUP_CONCAT(cmi.type) END as input_member_types
        #     FROM contexts_members cm
        #     LEFT JOIN contexts_members_inputs cmi
        #         ON cmi.member_id = cm.id
        #     WHERE cm.context_id = ?
        #     GROUP BY cm.id
        # """
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
            GROUP BY cm.id
        """
        # cont = self.parent.parent
        members_data = sql.get_results(query, (self.parent.parent.context.id,))  # Pass the current context ID

        # Iterate over the fetched members and add them to the scene
        for id, agent_id, agent_config, loc_x, loc_y, member_inp_str, member_type_str in members_data:
            member = DraggableAgent(id, self, loc_x, loc_y, member_inp_str, member_type_str, agent_config)

            self.scene.addItem(member)
            self.members[id] = member

    def load_member_inputs(self):
        for _, line in self.lines.items():
            self.scene.removeItem(line)
        self.lines = {}

        for m_id, member in self.members.items():
            for input_member_id, input_type in member.member_inputs.items():
                if input_member_id == 0:
                    input_member = self.user_bubble
                else:
                    input_member = self.members[input_member_id]
                key = (m_id, input_member_id)
                line = ConnectionLine(key, member.input_point, input_member.output_point, input_type)
                self.scene.addItem(line)
                self.lines[key] = line

    def select_ids(self, ids):
        # unselect all items
        for item in self.scene.selectedItems():
            item.setSelected(False)
        # select all items with ids
        for _id in ids:
            self.members[_id].setSelected(True)

    def delete_ids(self, ids):
        self.select_ids(ids)
        # press delete button
        self.view.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier))

    def insertAgent(self, item):
        self.group_topbar.dlg.close()

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
        if input_member_id == 0:  # todo rewrite
            # pass
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
            # input_member_id = None if input_member_id == 0 else input_member_id
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
        self.load()

    def add_member(self):
        # insert self.new_agent into contexts_members table
        sql.execute("""
            INSERT INTO contexts_members
                (context_id, agent_id, agent_config, loc_x, loc_y)
            SELECT
                ?, id, config, ?, ?
            FROM agents
            WHERE id = ?""", (self.parent.parent.context.id, self.new_agent.x(), self.new_agent.y(), self.new_agent.id))

        self.scene.removeItem(self.new_agent)
        self.new_agent = None
        self.load()

    def on_selection_changed(self):
        # self.parent().parent.main.setUpdatesEnabled(False)
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

        # self.parent().parent.main.setUpdatesEnabled(True)


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
            primary_color_label = QLabel('Primary Color:')
            primary_color_label.setFixedWidth(220)  # Stops width changing when changing role
            self.primary_color_picker = ColorPickerButton()
            self.form_layout.addRow(primary_color_label, self.primary_color_picker)
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
            # self.load()
            # self.update_bubble_options()

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
            role_config['display.bubble_image_size'] = int(self.bubble_image_size_input.text())
            sql.execute("""UPDATE roles SET `config` = ? WHERE id = ? """, (json.dumps(role_config), role_id,))
            self.parent.main.page_chat.context.load_context_settings()

        # def toggle_role_panels(self, role):
        #     # Update labels and connections based on selected role
        #     self.update_bubble_options()

        # def update_bubble_options(self):

            # Update colorChanged connections
            # self.bubble_bg_color_picker.colorChanged.disconnect()
            # self.bubble_text_color_picker.colorChanged.disconnect()
            # self.bubble_bg_color_picker.colorChanged.connect(
            #     lambda color: self.parent.update_config(f'display.{role}_bubble_bg_color', color))
            # self.bubble_text_color_picker.colorChanged.connect(
            #     lambda color: self.parent.update_config(f'display.{role}_bubble_text_color', color))

        def load(self):
            with block_signals(self):
                self.primary_color_picker.set_color(config.get_value('display.primary_color'))
                self.secondary_color_picker.set_color(config.get_value('display.secondary_color'))
                self.text_color_picker.set_color(config.get_value('display.text_color'))
                self.text_font_dropdown.setCurrentText(config.get_value('display.text_font'))
                self.text_size_input.setValue(config.get_value('display.text_size'))
                # self.bubble_bg_color_picker.set_color(config.get_value('display.user_bubble_bg_color'))
                # self.bubble_text_color_picker.set_color(config.get_value('display.user_bubble_text_color'))

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

            # def sizeHint(self, option, index):  # todo - check
            #     return super().sizeHint(option, index)

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
                    priv_key
                FROM apis""")
            for row_data in data:
                row_position = self.table.rowCount()
                self.table.insertRow(row_position)
                for column, item in enumerate(row_data):
                    self.table.setItem(row_position, column, QTableWidgetItem(str(item)))

            self.table.blockSignals(False)

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

            self.layout.addWidget(self.main_content, stretch=1)

        class Button_New_Model(QPushButton):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent
                self.clicked.connect(self.new_model)
                self.icon = QIcon(QPixmap(":/resources/icon-new.png"))  # Path to your icon
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
                    sql.execute("INSERT INTO `models` (`name`, `api_id`, `model_name`) VALUES (?, ?, '')", (text, self.parent.api_combo_box.currentData(),))
                    self.parent.load_models()
                PIN_STATE = current_pin_state

        class Button_Delete_Model(QPushButton):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent
                self.clicked.connect(self.delete_model)
                self.icon = QIcon(QPixmap(":/resources/icon-delete.png"))
                self.setIcon(self.icon)
                self.setFixedSize(25, 25)
                self.setIconSize(QSize(25, 25))

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


class AgentSettings(QWidget):
    def __init__(self, parent, is_context_member_agent=False):
        super().__init__(parent=parent)
        self.parent = parent
        self.is_context_member_agent = is_context_member_agent
        self.agent_id = 0
        self.agent_config = {}

        self.settings_sidebar = self.Agent_Settings_SideBar(parent=self)

        self.content = QStackedWidget(self)
        self.page_general = self.Page_General_Settings(self)
        self.page_context = self.Page_Context_Settings(self)
        self.page_actions = self.Page_Actions_Settings(self)
        self.page_group = self.Page_Group_Settings(self)
        # self.page_code = self.Page_Plugins_Settings(self)
        self.page_voice = self.Page_Voice_Settings(self)
        self.content.addWidget(self.page_general)
        self.content.addWidget(self.page_context)
        self.content.addWidget(self.page_actions)
        self.content.addWidget(self.page_group)
        # self.content.addWidget(self.page_code)
        self.content.addWidget(self.page_voice)

        # H layout for lsidebar and content
        self.input_layout = QHBoxLayout(self)
        self.input_layout.addWidget(self.settings_sidebar)
        self.input_layout.addWidget(self.content)

        # input_container = QWidget()
        # input_container.setLayout(input_layout)

    def get_current_config(self):
        # ~CONF
        hh = 1
        # Retrieve the current values from the widgets and construct a new 'config' dictionary
        current_config = {
            'general.avatar_path': self.page_general.avatar_path,
            'general.use_plugin': self.page_general.plugin_combo.currentData(),
            'context.model': self.page_context.model_combo.currentData(),
            'context.sys_msg': self.page_context.sys_msg.toPlainText(),
            'context.fallback_to_davinci': self.page_context.fallback_to_davinci.isChecked(),
            'context.max_messages': self.page_context.max_messages.value(),
            'context.auto_title': self.page_context.auto_title.isChecked(),
            'context.display_markdown': self.page_context.display_markdown.isChecked(),
            'actions.enable_actions': self.page_actions.enable_actions.isChecked(),
            'actions.source_directory': self.page_actions.source_directory.text(),
            'actions.replace_busy_action_on_new': self.page_actions.replace_busy_action_on_new.isChecked(),
            'actions.use_function_calling': self.page_actions.use_function_calling.isChecked(),
            'actions.use_validator': self.page_actions.use_validator.isChecked(),
            'actions.code_auto_run_seconds': self.page_actions.code_auto_run_seconds.text(),
            'group.hide_responses': self.page_group.hide_responses.isChecked(),
            'group.default_context_placeholder': self.page_group.default_context_placeholder.text(),
            'voice.current_id': int(self.page_voice.current_id),
        }
        return json.dumps(current_config)

    def update_agent_config(self):
        current_config = self.get_current_config()
        if self.is_context_member_agent:
            sql.execute("UPDATE contexts_members SET agent_config = ? WHERE id = ?", (current_config, self.agent_id))
        else:
            sql.execute("UPDATE agents SET config = ? WHERE id = ?", (current_config, self.agent_id))
        # self.main.page_chat.context
        self.agent_config = json.loads(current_config)
        self.load()

    def load(self):
        with block_signals(self.page_general, self.page_context, self.page_actions):  # , self.page_code):
            self.page_general.load()
            self.page_context.load()
            self.page_actions.load()
            self.page_group.load()
            self.page_voice.load()
            self.settings_sidebar.refresh_warning_label()
            # self.page_code.load()

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

            self.btn_general = self.Settings_SideBar_Button(self, text='General')
            self.btn_general.setFont(font)
            self.btn_general.setChecked(True)
            self.btn_context = self.Settings_SideBar_Button(self, text='Context')
            self.btn_context.setFont(font)
            self.btn_actions = self.Settings_SideBar_Button(self, text='Actions')
            self.btn_actions.setFont(font)
            self.btn_group = self.Settings_SideBar_Button(self, text='Group')
            self.btn_group.setFont(font)
            self.btn_voice = self.Settings_SideBar_Button(self, text='Voice')
            self.btn_voice.setFont(font)

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

            self.warning_label = QLabel("Note:\nA plugin is enabled, these settings may not work as expected")
            self.warning_label.setFixedWidth(100)
            self.warning_label.setWordWrap(True)
            self.warning_label.setStyleSheet("color: gray;")
            self.warning_label.setAlignment(Qt.AlignCenter)
            self.warning_label.hide()

            self.layout.addWidget(self.btn_general)
            self.layout.addWidget(self.btn_context)
            self.layout.addWidget(self.btn_actions)
            self.layout.addWidget(self.btn_group)
            self.layout.addWidget(self.btn_voice)
            self.layout.addStretch()
            self.layout.addWidget(self.warning_label)
            self.layout.addStretch()

        def onButtonToggled(self, button, checked):
            if checked:
                index = self.button_group.id(button)
                self.parent.content.setCurrentIndex(index)
                self.parent.content.currentWidget().load()
                self.refresh_warning_label()

        def refresh_warning_label(self):
            index = self.parent.content.currentIndex()
            show_plugin_warning = index > 0 and self.parent.agent_config.get('general.use_plugin', '') != ''
            if show_plugin_warning:
                self.warning_label.show()
            else:
                self.warning_label.hide()

        class Settings_SideBar_Button(QPushButton):
            def __init__(self, parent, text=''):
                super().__init__(parent=parent)
                self.setProperty("class", "menuitem")
                # self.clicked.connect(self.goto_system_settings)
                self.setText(text)
                self.setFixedSize(75, 30)
                self.setCheckable(True)

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
            self.name.textChanged.connect(self.update_name)

            font = self.name.font()
            font.setPointSize(15)
            self.name.setFont(font)

            self.name.setAlignment(Qt.AlignCenter)

            # Create a combo box for the plugin selection
            self.plugin_combo = PluginComboBox()
            self.plugin_combo.setFixedWidth(150)
            self.plugin_combo.setItemDelegate(AlignDelegate(self.plugin_combo))

            self.plugin_combo.currentIndexChanged.connect(self.plugin_changed)

            # Adding avatar and name to the main layout
            profile_layout.addWidget(self.avatar)  # Adding the avatar

            # add profile layout to main layout
            main_layout.addLayout(profile_layout)
            main_layout.addWidget(self.name)
            main_layout.addWidget(self.plugin_combo, alignment=Qt.AlignCenter)
            main_layout.addStretch()

        def load(self):
            parent = self.parent
            agent_page = self.parent.parent

            with block_signals(self):
                self.avatar_path = (parent.agent_config.get('general.avatar_path', ''))
                try:
                    if parent.page_general.avatar_path == '':
                        raise Exception('No avatar path')
                    unsimp_path = unsimplify_path(self.avatar_path)
                    # print(f'Unsimplified {self.avatar_path} to {unsimp_path}')
                    # print(unsimp_path)
                    avatar_img = QPixmap(unsimp_path)
                except Exception as e:
                    avatar_img = QPixmap(":/resources/icon-agent.png")
                self.avatar.setPixmap(avatar_img)
                self.avatar.update()

                if not self.parent.is_context_member_agent:
                    current_row = agent_page.table_widget.currentRow()
                    name_cell = agent_page.table_widget.item(current_row, 3)
                    if name_cell:
                        self.name.setText(name_cell.text())

                active_plugin = parent.agent_config.get('general.use_plugin', '')
                # W, set plugin combo by key
                for i in range(self.plugin_combo.count()):
                    if self.plugin_combo.itemData(i) == active_plugin:
                        self.plugin_combo.setCurrentIndex(i)
                        break
                else:
                    self.plugin_combo.setCurrentIndex(0)

        def update_name(self):
            new_name = self.name.text()
            sql.execute("UPDATE agents SET name = ? WHERE id = ?", (new_name, self.parent.agent_id))
            # self.parent.load()
            self.parent.parent.load()
            # self.parent.parent.main.page_chat.context.load()

        def plugin_changed(self):
            self.parent.update_agent_config()
            # set first item text to 'No Plugin' if no plugin is selected
            if self.plugin_combo.currentData() == '':
                self.plugin_combo.setItemText(0, "Choose Plugin")
            else:
                self.plugin_combo.setItemText(0, "< No Plugin >")

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

            self.form_layout.addRow(QLabel('Model:'), self.model_combo)

            self.sys_msg = QTextEdit()
            self.sys_msg.setFixedHeight(150)  # Adjust height as per requirement
            self.form_layout.addRow(QLabel('System message:'), self.sys_msg)

            self.fallback_to_davinci = QCheckBox()
            self.form_layout.addRow(QLabel('Fallback to davinci:'), self.fallback_to_davinci)

            self.max_messages = QSpinBox()
            self.max_messages.setFixedWidth(150)  # Consistent width
            self.form_layout.addRow(QLabel('Max messages:'), self.max_messages)

            self.auto_title = QCheckBox()
            self.form_layout.addRow(QLabel('Auto title:'), self.auto_title)

            self.display_markdown = QCheckBox()
            self.form_layout.addRow(QLabel('Display markdown:'), self.display_markdown)

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
            self.display_markdown.stateChanged.connect(parent.update_agent_config)

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
                self.display_markdown.setChecked(parent.agent_config.get('context.display_markdown', False))

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

            self.form_layout = QFormLayout()

            self.label_hide_responses = QLabel('Hide responses:')
            self.label_default_context_placeholder = QLabel('Default context placeholder:')

            self.hide_responses = QCheckBox()
            self.form_layout.addRow(self.label_hide_responses, self.hide_responses)

            self.default_context_placeholder = QLineEdit()
            self.form_layout.addRow(self.label_default_context_placeholder, self.default_context_placeholder)

            self.setLayout(self.form_layout)

            self.hide_responses.stateChanged.connect(parent.update_agent_config)
            self.default_context_placeholder.textChanged.connect(parent.update_agent_config)

        def load(self):
            parent = self.parent
            with block_signals(self):
                self.hide_responses.setChecked(parent.agent_config.get('group.hide_responses', False))
                self.default_context_placeholder.setText(str(parent.agent_config.get('group.default_context_placeholder', '')))

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

            self.current_id = 0
            self.load_data_from_db()

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
            # todo - Implement functionality to test the voice
            pass


class Page_Agents(ContentPage):
    def __init__(self, main):
        super().__init__(main=main, title='Agents')
        self.main = main

        # self.agent_id = 0
        # self.agent_config = {}

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
                r_config = json.loads(row_data[2])
                agent_avatar_path = r_config.get('general.avatar_path', '')

                try:
                    if agent_avatar_path == '':
                        raise Exception('No avatar path')
                    agent_avatar_path = unsimplify_path(agent_avatar_path)
                    avatar_img = QPixmap(agent_avatar_path)
                except Exception as e:
                    avatar_img = QPixmap(":/resources/icon-agent.png")

                circular_avatar_pixmap = create_circular_pixmap(avatar_img, diameter=25)

                # Create a QLabel to hold the pixmap
                avatar_label = QLabel()
                avatar_label.setPixmap(circular_avatar_pixmap)
                # set background to transparent
                avatar_label.setAttribute(Qt.WA_TranslucentBackground, True)

                # Add the new avatar icon column after the ID column
                self.table_widget.setCellWidget(row_position, 1, avatar_label)

                btn_chat = QPushButton('')
                btn_chat.setIcon(icon_chat)
                btn_chat.setIconSize(QSize(25, 25))
                btn_chat.clicked.connect(partial(self.chat_with_agent, row_data))
                self.table_widget.setCellWidget(row_position, 4, btn_chat)

                btn_del = QPushButton('')
                btn_del.setIcon(icon_del)
                btn_del.setIconSize(QSize(25, 25))
                btn_del.clicked.connect(partial(self.delete_agent, row_data))
                self.table_widget.setCellWidget(row_position, 5, btn_del)

                # Connect the double-click signal with the chat button click
                self.table_widget.itemDoubleClicked.connect(self.on_row_double_clicked)

        if self.table_widget.rowCount() > 0:
            if self.agent_settings.agent_id > 0:
                for row in range(self.table_widget.rowCount()):
                    if self.table_widget.item(row, 0).text() == str(self.agent_settings.agent_id):
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

        self.agent_settings.agent_id = int(self.table_widget.item(current_row, 0).text())
        self.agent_settings.agent_config = json.loads(agent_config_json) if agent_config_json else {}
        self.agent_settings.load()

    def chat_with_agent(self, row_data):
        self.main.content.setCurrentWidget(self.main.page_chat)
        self.main.sidebar.btn_new_context.setChecked(True)
        from agentpilot.context.base import Context
        id_value = row_data[0]  # self.table_widget.item(row_item, 0).text()
        self.main.page_chat.new_context(agent_id=id_value)
        # self.main.page_chat.context = Context(agent_id=id_value)
        # self.main.page_chat.reload()

    def delete_agent(self, row_data):
        global PIN_STATE
        context_count = sql.get_scalar("""
            SELECT
                COUNT(*)
            FROM contexts_members
            WHERE agent_id = ?""", (row_data[0],))

        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Delete Agent")
        if context_count > 0:
            msg.setText(f"Cannot delete '{row_data[3]}' because they exist in {context_count} contexts.")
            msg.setStandardButtons(QMessageBox.Ok)
        else:
            msg.setText(f"Are you sure you want to delete this agent?")
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

        current_pin_state = PIN_STATE
        PIN_STATE = True
        retval = msg.exec_()
        PIN_STATE = current_pin_state
        if retval != QMessageBox.Yes:
            return

        sql.execute("DELETE FROM contexts_messages WHERE context_id IN (SELECT id FROM contexts WHERE agent_id = ?);", (row_data[0],))
        sql.execute("DELETE FROM contexts WHERE agent_id = ?;", (row_data[0],))
        sql.execute('DELETE FROM contexts_members WHERE context_id = ?', (row_data[0],))
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


class Page_Contexts(ContentPage):
    def __init__(self, main):
        super().__init__(main=main, title='Contexts')
        self.main = main

        self.table_widget = QTableWidget(0, 5, self)

        self.table_widget.setColumnWidth(3, 45)
        self.table_widget.setColumnWidth(4, 45)
        self.table_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_widget.hideColumn(0)
        self.table_widget.horizontalHeader().hide()
        self.table_widget.verticalHeader().hide()
        self.table_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)

        palette = self.table_widget.palette()
        palette.setColor(QPalette.Highlight, QColor(SECONDARY_COLOR))
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        palette.setColor(QPalette.Text, QColor(TEXT_COLOR))
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
                CASE WHEN cm.latest_message_id IS NULL THEN 0 ELSE 1 END,
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
            btn_chat.clicked.connect(partial(self.chat_with_context, row_data))
            self.table_widget.setCellWidget(row_position, 3, btn_chat)

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

    def chat_with_context(self, row_item):
        id_value = row_item[0]
        self.main.page_chat.goto_context(context_id=id_value)
        self.main.content.setCurrentWidget(self.main.page_chat)
        self.main.sidebar.btn_new_context.setChecked(True)

    def delete_context(self, row_item):
        from agentpilot.context.base import Context
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
        sql.execute("DELETE FROM contexts_messages WHERE context_id = ?;", (context_id,))  # todo update delete to cascade branches
        sql.execute("DELETE FROM contexts WHERE id = ?;", (context_id,))
        sql.execute('DELETE FROM contexts_members WHERE context_id = ?', (context_id,))
        self.load()

        if self.main.page_chat.context.id == context_id:
            self.main.page_chat.context = Context()


class Page_Chat(QScrollArea):
    def __init__(self, main):
        super().__init__(parent=main)
        from agentpilot.context.base import Context
        # self.agent = Agent(agent_id=None)
        self.context = Context()
        self.main = main
        # self.setFocusPolicy(Qt.StrongFocus)

        self.threadpool = QThreadPool()

        self.receive_worker = None
        self.chat_bubbles = []
        self.last_assistant_msg = None

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
        # self.chat_scroll_layout.setSpacing(0)
        self.chat_scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_scroll_layout.addStretch(1)

        # spacer = QSpacerItem(0, 20, QSizePolicy.Minimum, QSizePolicy.Fixed)
        # self.chat_scroll_layout.addSpacerItem(spacer)

        self.scroll_area.setWidget(self.chat)
        self.scroll_area.setWidgetResizable(True)

        self.layout.addWidget(self.scroll_area)

        self.installEventFilterRecursively(self)

        self.temp_text_size = None

        self.decoupled_scroll = False

    def reload(self, is_first_load=False):
        last_container = self.chat_bubbles[-1] if self.chat_bubbles else None
        last_bubble_msg_id = last_container.bubble.msg_id if last_container else 0
        messages = self.context.message_history.messages
        for msg in messages:
            if msg.id <= last_bubble_msg_id:
                continue
            self.insert_bubble(msg, is_first_load=is_first_load)

        QTimer.singleShot(1, self.scroll_to_end)

        self.topbar.load()

    def load(self):
        self.clear_bubbles()
        self.reload()

    def clear_bubbles(self):
        while self.chat_bubbles:
            bubble = self.chat_bubbles.pop()
            self.chat_scroll_layout.removeWidget(bubble)
            bubble.deleteLater()

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
                is_generating = self.threadpool.activeThreadCount() > 0
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
        # self.load_bubbles()  # todo instead of reloading bubbles just reapply style
        # self.setFocus()

    def temp_zoom_out(self):
        if not self.temp_text_size:
            self.temp_text_size = config.get_value('display.text_size')
        if self.temp_text_size <= 7:
            return
        self.temp_text_size -= 1
        # self.main.page_settings.update_config('display.text_size', self.temp_text_size)
        # self.load_bubbles()  # todo instead of reloading bubbles just reapply style
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
# If
    class Top_Bar(QWidget):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.setMouseTracking(True)
            # self.setFixedHeight(40)

            self.settings_layout = QVBoxLayout(self)   # Main layout for this widget
            self.settings_layout.setSpacing(0)
            self.settings_layout.setContentsMargins(0,0,0,0)

            top_bar_container = QWidget()
            self.topbar_layout = QHBoxLayout(top_bar_container)
            self.topbar_layout.setSpacing(0)
            self.topbar_layout.setContentsMargins(5, 5, 5, 10)

            input_container = QWidget()
            input_container.setFixedHeight(40)
            input_container.setLayout(self.topbar_layout)

            self.settings_open = False
            self.group_settings = GroupSettings(self)
            self.group_settings.hide()

            self.settings_layout.addWidget(input_container)
            self.settings_layout.addWidget(self.group_settings)
            self.settings_layout.addWidget(top_bar_container)

            agent_avatar_path = ''
            try:
                if agent_avatar_path == '':
                    raise Exception('No avatar path')
                avatar_img = QPixmap(agent_avatar_path)
            except Exception as e:
                avatar_img = QPixmap(":/resources/icon-agent.png")

            circular_pixmap = create_circular_pixmap(avatar_img)

            self.profile_pic_label = QLabel(self)
            self.profile_pic_label.setPixmap(circular_pixmap)
            self.profile_pic_label.setFixedSize(50, 30)

            self.topbar_layout.addWidget(self.profile_pic_label)
            # conect profile label click to method 'open'
            self.profile_pic_label.mousePressEvent = self.agent_name_clicked

            self.agent_name_label = QLabel(self)
            self.agent_name_label.setText(parent.context.chat_name)
            font = self.agent_name_label.font()
            font.setPointSize(15)
            self.agent_name_label.setFont(font)
            self.agent_name_label.setStyleSheet("QLabel:hover { color: #dddddd; }")
            self.agent_name_label.mousePressEvent = self.agent_name_clicked
            self.agent_name_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            # self.agent_name_label.setFixedHeight(40)
            self.topbar_layout.addWidget(self.agent_name_label)

            self.topbar_layout.addStretch()

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

            button_layout.addWidget(self.btn_prev_context)
            button_layout.addWidget(self.btn_next_context)

            # Add the container to the top bar layout
            self.topbar_layout.addWidget(self.button_container)

            self.button_container.hide()

        def load(self):
            self.group_settings.load()

        def previous_context(self):
            context_id = self.parent.context.id
            prev_context_id = sql.get_scalar("SELECT id FROM contexts WHERE id < ? AND parent_id IS NULL ORDER BY id DESC LIMIT 1;", (context_id,))
            if prev_context_id:
                self.parent.goto_context(prev_context_id)
                self.btn_next_context.setEnabled(True)
            else:
                self.btn_prev_context.setEnabled(False)

        def next_context(self):
            context_id = self.parent.context.id
            next_context_id = sql.get_scalar("SELECT id FROM contexts WHERE id > ? AND parent_id IS NULL ORDER BY id LIMIT 1;", (context_id,))
            if next_context_id:
                self.parent.goto_context(next_context_id)
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
                self.group_settings.show()  # Show the GroupSettings page
                # self.setFixedHeight(100)
            else:
                self.group_settings.hide()
                # self.setFixedHeight(40)

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
                avatar_img = QPixmap(":/resources/icon-agent.png")

            # Create a circular profile picture
            circular_pixmap = create_circular_pixmap(avatar_img)

            # Update the QLabel with the new pixmap
            self.profile_pic_label.setPixmap(circular_pixmap)

        # class GroupSettings(QWidget):
        #     def __init__(self, parent):
        #         super().__init__(parent)
        #         self.context = parent.parent.context
        #         self.setLayout(QVBoxLayout())


    def on_button_click(self):
        self.send_message(self.main.message_text.toPlainText(), clear_input=True)

    def send_message(self, message, role='user', clear_input=False):  # role output and note are broken for now, todo add global / local option
        global PIN_STATE
        if self.threadpool.activeThreadCount() > 0:
            self.receive_worker.stop()
            # self.receive_worker.wait()
            return
        try:
            new_msg = self.context.save_message(role, message)
        except Exception as e:
            # show error message box
            old_pin_state = PIN_STATE
            PIN_STATE = True
            QMessageBox.critical(self, "Error", "OpenAI API Error: " + str(e))
            PIN_STATE = old_pin_state
            return

        if not new_msg:
            return

        if clear_input:
            # QTimer.singleShot(1, self.main.message_text.clear)
            QTimer.singleShot(1, self.main.message_text.clear)
            self.main.message_text.setFixedHeight(51)
            self.main.send_button.setFixedHeight(51)

        if role == 'user':
            msg = Message(msg_id=new_msg.id, role='user', content=new_msg.content)
            self.main.new_bubble_signal.emit(msg)
            # self.main.new_bubble_signal.emit({'id': new_msg.id, 'role': 'user', 'content': new_msg.content})
            # QApplication.processEvents()
            self.scroll_to_end()
            # QApplication.processEvents()

        # Create and start the thread, and connect signals to slots.
        self.main.send_button.update_icon(is_generating=True)
        # icon_iden = 'send' if not is_generating else 'stop'
        # icon = QIcon(QPixmap(f":/resources/icon-stop.png"))
        # self.main.send_button.setIcon(icon)

        self.receive_worker = self.ReceiveWorker(self.context)
        self.receive_worker.signals.new_sentence_signal.connect(self.on_new_sentence)
        self.receive_worker.signals.finished_signal.connect(self.on_receive_finished)
        self.threadpool.start(self.receive_worker)

        # self.load_new_code_bubbles()
        #
        # if auto_title:
        #     self.agent.context.generate_title()

    def on_new_sentence(self, chunk):
        # This slot will be called when the new_sentence_signal is emitted.
        self.main.new_sentence_signal.emit(chunk)  # todo Checkpoint
        if not self.decoupled_scroll:
            self.scroll_to_end()
            QApplication.processEvents()

    def on_receive_finished(self):
        self.load()

        # auto_title = self.agent.config.get('context.auto_title', True)
        # if not self.agent.context.message_history.count() == 1:
        #     auto_title = False
        #
        # if auto_title:
        #     self.agent.context.generate_title()  # todo reimplenent

        self.main.send_button.update_icon(is_generating=False)
        self.decoupled_scroll = False

    @Slot(dict)
    def insert_bubble(self, message=None, is_first_load=False, index=None):
        msg_container = self.MessageContainer(self, message=message, is_first_load=is_first_load)

        if message.role == 'assistant':
            self.last_assistant_msg = msg_container
        else:
            self.last_assistant_msg = None

        if index is None:
            index = len(self.chat_bubbles) # - 1

        self.chat_bubbles.insert(index, msg_container)
        self.chat_scroll_layout.insertWidget(index, msg_container)

        return msg_container

    @Slot(str)
    def new_sentence(self, sentence):
        if self.last_assistant_msg is None:
            # new_assistant_msg_id = sql.execute("INSERT INTO contexts_messages (context_id, agent_id, role, content) VALUES (?, ?, ?, ?);", (self.context.id, self.context.agent_id, 'assistant', sentence))
            msg = Message(msg_id=-1, role='assistant', content=sentence)
            self.main.new_bubble_signal.emit(msg)
            # self.main.new_bubble_signal.emit({'id': -1, 'role': 'assistant', 'content': sentence})
        else:
            self.last_assistant_msg.bubble.append_text(sentence)

    def delete_messages_after(self, msg_id):
        # if incl_msg:
        if msg_id == 19:
            pass
        while self.chat_bubbles:
            cont = self.chat_bubbles.pop()
            bubble = cont.bubble
            self.chat_scroll_layout.removeWidget(cont)
            cont.deleteLater()
            if bubble.msg_id == msg_id:
                break

        # else:
        #     while self.chat_bubbles:
        #         last = self.chat_bubbles.pop()
        #         if last.bubble.msg_id == msg_id:
        #             break
        #         cont = self.chat_bubbles.pop()
        #         self.chat_scroll_layout.removeWidget(cont)
        #         cont.deleteLater()

        index = -1  # todo dirty, change Messages() list
        for i in range(len(self.context.message_history.messages)):
            msg = self.context.message_history.messages[i]
            if msg.id == msg_id:
                index = i
                break

        # if not incl_msg:
        #     index += 1 # todo when its the last message edge case
        if index <= len(self.context.message_history.messages) - 1:
            self.context.message_history.messages[:] = self.context.message_history.messages[:index]

    def scroll_to_end(self):
        QApplication.processEvents()  # process GUI events to update content size
        scrollbar = self.main.page_chat.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum() + 20)
        # QApplication.processEvents()

    def new_context(self, copy_context_id=None, agent_id=None):
        sql.execute("INSERT INTO contexts (id) VALUES (NULL)")
        context_id = sql.get_scalar("SELECT MAX(id) FROM contexts")
        if copy_context_id:
            copied_cm_id_list = sql.get_results("""
                SELECT
                    cm.id
                FROM contexts_members cm
                WHERE cm.context_id = ?
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
                ORDER BY cm.id""",
            (context_id, copy_context_id))

            pasted_cm_id_list = sql.get_results("""
                SELECT
                    cm.id
                FROM contexts_members cm
                WHERE cm.context_id = ?
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
                cmi[2] = 'NULL' if cmi[2] is None else mapped_cm_id_dict[cmi[2]]

                sql.execute("""
                    INSERT INTO contexts_members_inputs
                        (member_id, input_member_id, type)
                    VALUES
                        (?, ?, ?)""", (cmi[1], cmi[2], cmi[3]))

        elif agent_id is not None:
            sql.execute("""
                INSERT INTO contexts_members
                    (context_id, agent_id, agent_config, loc_x, loc_y)
                SELECT
                    ?, id, config, ?, ?
                FROM agents
                WHERE id = ?""", (context_id, 60, 140, agent_id))
        
        self.goto_context(context_id)

    def goto_context(self, context_id):
        from agentpilot.context.base import Context
        self.main.page_chat.context = Context(context_id=context_id)
        self.main.page_chat.load()

    class MessageContainer(QWidget):
        # Container widget for the profile picture and bubble
        def __init__(self, parent, message, is_first_load=False):
            super().__init__(parent=parent)
            self.parent = parent
            self.setProperty("class", "message-container")

            self.layout = QHBoxLayout(self)
            self.layout.setSpacing(0)
            self.layout.setContentsMargins(0, 0, 0, 0)
            self.bubble = self.create_bubble(message, is_first_load)

            agent_avatar_path = parent.context.participants.get(message.agent_id, {}).get('general.avatar_path', '')
            try:
                if agent_avatar_path == '':
                    raise Exception('No avatar path')
                avatar_img = QPixmap(agent_avatar_path)
            except Exception as e:
                avatar_img = QPixmap(":/resources/icon-agent.png")

            diameter = parent.context.roles.get(message.role, {}).get('display.bubble_image_size', 30)
            circular_pixmap = create_circular_pixmap(avatar_img, diameter)

            self.profile_pic_label = QLabel(self)
            self.profile_pic_label.setPixmap(circular_pixmap)
            self.profile_pic_label.setFixedSize(40, 30)

            self.layout.addWidget(self.profile_pic_label)
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

        def create_bubble(self, message, is_first_load=False):
            page_chat = self.parent

            params = {'msg_id': message.id, 'text': message.content, 'viewport': page_chat, 'role': message.role, 'parent': self}
            if message.role == 'user':
                bubble = page_chat.MessageBubbleUser(**params)
            elif message.role == 'code':
                params['start_timer'] = not is_first_load
                bubble = page_chat.MessageBubbleCode(**params)
            else:
                bubble = page_chat.MessageBubbleBase(**params)

            return bubble

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
                # Create new context with branch_msg_id and parent_id
                branch_msg_id = self.parent.branch_msg_id
                # parent_context_id = self.parent.parent.context.leaf_id

                sql.deactivate_all_branches_with_msg(self.parent.bubble.msg_id)
                sql.execute("INSERT INTO contexts (parent_id, branch_msg_id) SELECT context_id, ? FROM contexts_messages WHERE id = ?",
                            (branch_msg_id, branch_msg_id,))
                self.parent.parent.context.leaf_id = sql.get_scalar('SELECT MAX(id) FROM contexts')

                page_chat = self.parent.parent
                msg_to_send = self.parent.bubble.toPlainText()

                page_chat.delete_messages_after(self.parent.bubble.msg_id)

                page_chat.send_message(msg_to_send, clear_input=False)

                # # parent_context_id =  # current context parent if has branches else bubble.context_id
                # # sql.execute("INSERT INTO contexts (parent_id, branch_msg_id,active) VALUES (?, ?, 1);",
                # #             (self.parent.parent.context.id, self.parent.bubble.msg_id))
                # # Update context()
                # # Copy bubble message
                # # Remove following bubbles
                # # Send msg
                # popup = QMessageBox()
                # popup.setWindowTitle("Coming Soon")
                # popup.setText(str(branch_msg_id))
                # popup.setIcon(QMessageBox.Information)
                # popup.setStandardButtons(QMessageBox.Ok)
                # popup.exec_()

            def check_and_toggle(self):
                if self.parent.bubble.toPlainText() != self.parent.bubble.original_text:
                    self.show()
                else:
                    self.hide()

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
            # self.branch_msg_id = None
            # self.agent = parent.agent
            self.agent_config = {}
            self.role = role
            self.setProperty("class", "bubble")
            self.setProperty("class", role)
            self._viewport = viewport
            self.margin = QMargins(6, 0, 6, 0)
            self.text = ''
            self.original_text = text
            self.enable_markdown = self.agent_config.get('context.display_markdown', False)
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
            self.text += text
            self.original_text = self.text
            self.setMarkdownText(self.text)
            self.update_size()

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
            # self.update_size()

        # class BubbleButton_Resend(QPushButton):
        #     def __init__(self, parent=None):
        #         super().__init__(parent=parent)
        #         self.setProperty("class", "resend")
        #         self.clicked.connect(self.resend_msg)
        #
        #         icon = QIcon(QPixmap(":/resources/icon-send.png"))
        #         self.setIcon(icon)
        #
        #     def resend_msg(self):
        #         # Create new context with branch_msg_id and parent_id
        #         # Update context()
        #         # Copy bubble message
        #         # Remove following bubbles
        #         # Send msg
        #         popup = QMessageBox()
        #         popup.setWindowTitle("Coming Soon")
        #         popup.setText("This feature is coming soon!")
        #         popup.setIcon(QMessageBox.Information)
        #         popup.setStandardButtons(QMessageBox.Ok)
        #         popup.exec_()

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
                # self.btn_back.setCursor(Qt.PointingHandCursor)
                # self.btn_next.setCursor(Qt.PointingHandCursor)

                # # any branch button is under the mouse, set the cursor
                # if self.btn_back.underMouse() or self.btn_next.underMouse():
                #     print('chchchc')

                self.btn_back.setStyleSheet("QPushButton { background-color: none; } QPushButton:hover { background-color: #555555;}")
                self.btn_next.setStyleSheet("QPushButton { background-color: none; } QPushButton:hover { background-color: #555555;}")

                self.btn_back.move(6, 0)
                self.btn_next.move(36, 0)

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
            # def enterEvent(self, event):
            #     if self.btn_back.underMouse() or self.btn_next.underMouse():
            #         print('Mouse is over a button')
            #     super().enterEvent(event)
            #
            # def leaveEvent(self, event):
            #     print('Mouse left the widget')
            #     super().leaveEvent(event)

            def back(self):
                if self.bubble_id in self.branch_entry:
                    return
                else:
                    sql.deactivate_all_branches_with_msg(self.bubble_id)
                    current_index = self.child_branches.index(self.bubble_id)
                    if current_index == 0:
                        self.reload_following_bubbles()
                        return
                    next_msg_id = self.child_branches[current_index - 1]
                    sql.activate_branch_with_msg(next_msg_id)

                self.reload_following_bubbles()

            def next(self):
                if self.bubble_id in self.branch_entry:
                    activate_msg_id = self.child_branches[0]
                    sql.activate_branch_with_msg(activate_msg_id)
                else:
                    current_index = self.child_branches.index(self.bubble_id)
                    if current_index == len(self.child_branches) - 1:
                        return
                    sql.deactivate_all_branches_with_msg(self.bubble_id)
                    next_msg_id = self.child_branches[current_index + 1]
                    sql.activate_branch_with_msg(next_msg_id)

                self.reload_following_bubbles()

            def reload_following_bubbles(self):
                self.page_chat.delete_messages_after(self.bubble_id)
                # self.page_chat.context.message_history.delete_after(self.bubble_id, incl_msg=True)

                self.page_chat.context.message_history.load_messages()
                self.page_chat.load()

            def update_buttons(self):
                pass

    class MessageBubbleCode(MessageBubbleBase):
        def __init__(self, msg_id, text, viewport, role, parent, start_timer=False):
            super().__init__(msg_id, '', viewport, role, parent)

            self.lang, self.code = self.split_lang_and_code(text)
            self.original_text = self.code
            self.append_text(self.code)
            self.setToolTip(f'{self.lang} code')
            # self.tag = lang
            self.btn_rerun = self.BubbleButton_Rerun_Code(self)
            self.btn_rerun.setGeometry(self.calculate_button_position())
            self.btn_rerun.hide()

            if start_timer:
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
            self.countdown = int(self.agent_config.get('actions.code_auto_run_seconds', 5))  # 5  # Reset countdown to 5 seconds
            self.countdown_button.setText(f"{self.countdown}")
            # if self.main.parent().parent().expanded and not self.underMouse():
            if not self.underMouse():
                self.timer.start()  # Restart the timer

        def check_and_toggle_rerun_button(self):
            if self.underMouse():
                self.btn_rerun.show()
            else:
                self.btn_rerun.hide()

        def run_bubble_code(self):
            interpreter = self.parent.agent.active_plugin.agent_object
            output = interpreter.run_code(self.lang, self.code)

            # check if code message is the last in the context
            executed_msg_id = self.msg_id
            last_msg = self.parent.agent.context.message_history.last(incl_roles=('user', 'assistant', 'code', 'output'))
            if last_msg['id'] == executed_msg_id:
                self.parent.send_message(output, role='output')
                # self.parent.agent.save_message('output', output)

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

        class CountdownButton(QPushButton):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.setText(str(parent.agent.config.get('actions.code_auto_run_seconds', 5)))  # )
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

    class ReceiveWorker(QRunnable):
        class ReceiveWorkerSignals(QObject):
            new_sentence_signal = Signal(str)
            finished_signal = Signal()

        def __init__(self, context):
            super().__init__()

            self.context = context
            self.stop_requested = False
            self.signals = self.ReceiveWorkerSignals()

        def run(self):
            parallel_agents = next(self.context.iterator.cycle())

            if len(parallel_agents) == 1:
                self.receive_from_agent(parallel_agents[0])
            else:
                # Run each agent on a separate thread
                threads = []
                for agent in parallel_agents:
                    thread = Thread(target=self.receive_from_agent, args=(agent, ))
                    thread.start()
                    threads.append(thread)

                # Wait for all threads to finish
                for thread in threads:
                    thread.join()

            self.signals.finished_signal.emit()

        def stop(self):
            self.stop_requested = True

        def receive_from_agent(self, agent):  # todo check if context is written to
            for key, chunk in agent.receive(stream=True):
                if self.stop_requested:
                    break
                if key in ('assistant', 'message'):
                    self.signals.new_sentence_signal.emit(chunk)  # Emitting the signal with the new sentence.
                else:
                    break


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
            # self.main.page_chat.load()

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
#             super().__init__(parent=parent)
#             self.setFixedHeight(20)
#             self.setFixedWidth(20)
#             self.clicked.connect(self.toggle_personality)
#             self.icon = QIcon(QPixmap(":/resources/icon-drama-on.png"))
#             self.setIcon(self.icon)
#             self.setToolTip("Personality")
#
#         def toggle_personality(self):
#             global PERSONALITY_STATE
#             PERSONALITY_STATE = not PERSONALITY_STATE
#             icon_iden = "on" if PERSONALITY_STATE else "off"
#             icon_file = f":/resources/icon-drama-{icon_iden}.png"
#             self.icon = QIcon(QPixmap(icon_file))
#             self.setIcon(self.icon)
#
#     class ButtonBar_Jailbreak(QPushButton):
#         def __init__(self, parent=None):
#             super().__init__(parent=parent)
#             self.setFixedHeight(20)
#             self.setFixedWidth(20)
#             self.clicked.connect(self.toggle_personality)
#             self.icon = QIcon(QPixmap(":/resources/icon-jailbreak-on.png"))
#             self.setIcon(self.icon)
#             self.setToolTip("Jailbreak")
#
#         def toggle_personality(self):
#             global PERSONALITY_STATE
#             PERSONALITY_STATE = not PERSONALITY_STATE
#             icon_iden = "on" if PERSONALITY_STATE else "off"
#             icon_file = f":/resources/icon-jailbreak-{icon_iden}.png"
#             self.icon = QIcon(QPixmap(icon_file))
#             self.setIcon(self.icon)
#
#     class ButtonBar_OpenInterpreter(QPushButton):
#         def __init__(self, parent=None):
#             super().__init__(parent=parent)
#             self.setFixedHeight(20)
#             self.setFixedWidth(20)
#             self.clicked.connect(self.toggle_openinterpreter)
#             self.icon = QIcon(QPixmap(":/resources/icon-interpreter-on.png"))
#             self.setIcon(self.icon)
#             self.setToolTip("Open Interpreter")
#
#         def toggle_openinterpreter(self):
#             global OPEN_INTERPRETER_STATE
#             # 3 WAY TOGGLE
#             OPEN_INTERPRETER_STATE = ((OPEN_INTERPRETER_STATE + 1 + 1) % 3) - 1
#             icon_iden = "on" if OPEN_INTERPRETER_STATE == 0 else "forced" if OPEN_INTERPRETER_STATE == 1 else "off"
#             icon_file = f":/resources/icon-interpreter-{icon_iden}.png"
#             self.icon = QIcon(QPixmap(icon_file))
#             self.setIcon(self.icon)


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
    new_sentence_signal = Signal(str)

    mouseEntered = Signal()
    mouseLeft = Signal()

    def check_db(self):
        # Check if the database is available
        while not sql.check_database():
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

        # self.page_chat.agent = base_agent

        # self.sidebar_layout = QVBoxLayout(self.sidebar)
        # self.sidebar_layout.setContentsMargins(0, 0, 0, 0)
        # self.sidebar_layout.setSpacing(0)
        # self.sidebar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

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
