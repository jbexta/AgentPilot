import cProfile
import queue
import sys
import math
import threading
import time

from PySide6 import QtCore
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from agent.context import Message
from utils import config
from utils.sql import check_database

# import open
# import oa
# from agent.base import Agent

# setViewportUpdateMode to full

STYLE = """
QWidget {
    background-color: #363636;
    border-radius: 12px
}
QTextEdit {
    background-color: #535353;
    border-radius: 12px;
    color: #FFF;
}
QTextEdit.msgbox {
    background-color: #535353;
    border-radius: 12px;
    border-top-right-radius: 0px;
    border-bottom-right-radius: 0px;
}
QTextEdit.bubble {
    background-color: #535353;
    border-radius: 12px;
}
QPushButton.send {
    background-color: #535353;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    color: #FFF;
    margin-left: -8px;
}
QPushButton.send:hover {
    background-color: #537373;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    border-left: 1px solid black;
    color: #FFF;
    margin-left: -8px;
}
#TitleBarButtonMin {
    background-color: #333;
}
#TitleBarButtonMin:hover {
    background-color: #777;
}
QWidget.central {
    border-radius: 12px;
}
QTextEdit.user {
    color: #d1d1d1;
}
QTextEdit.assistant {
    color: #9bbbcf;
}
QScrollBar:vertical {
    width: 0px;
}
"""

BOTTOM_CORNER_X = 400
BOTTOM_CORNER_Y = 450


class TitleBar(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("TitleBarWidget")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMaximumHeight(40)
        sizePolicy = QSizePolicy()
        sizePolicy.setHorizontalPolicy(QSizePolicy.Policy.Fixed)
        self.minimizeButton = TitleBarButtonMin(parent=self)
        self.closeButton = TitleBarButtonClose(parent=self)
        # self.layout.addWidget(self.minimizeButton)
        # self.layout.addWidget(self.closeButton)
        self.layout = QHBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addStretch(1)
        self.layout.addWidget(self.minimizeButton)
        self.layout.addWidget(self.closeButton)
        self.setMouseTracking(True)
        self._pressed = False
        self._cpos = None
        # make the title bar transparent
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def setWindowIcon(self, icon):
        pixmap = QPixmap(icon)
        self.icon.setPixmap(pixmap)

    def mouseDoubleClickEvent(self, _):
        if self.window().isMaximized():
            self.window().showNormal()
        else:
            self.window().showMaximized()

    def mousePressEvent(self, event):
        self._pressed = True
        self._cpos = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if not self._pressed:
            return
        pos = event.position().toPoint()
        difx, dify = (pos - self._cpos).toTuple()
        geom = self.window().geometry()
        x, y, w, h = geom.x(), geom.y(), geom.width(), geom.height()
        new_coords = x + difx, y + dify, w, h
        self.window().setGeometry(*new_coords)

    def mouseReleaseEvent(self, event):
        self._pressed = False
        self._cpos = None


class TitleBarButtonMin(QPushButton):

    def __init__(self, parent=None):
        super().__init__(parent=parent, icon=QIcon())
        self.setFixedHeight(20)
        self.setFixedWidth(20)
        self.clicked.connect(self.window_action)
        self.icon = QIcon(QPixmap("./utils/resources/minus.png"))
        self.setIcon(self.icon)

    def window_action(self):
        if self.window().isMinimized():
            self.window().showNormal()
        else:
            self.window().showMinimized()


class TitleBarButtonClose(QPushButton):
    closeApp = Signal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setFixedHeight(20)
        self.setFixedWidth(20)
        self.clicked.connect(self.closeApp)
        self.icon = QIcon(QPixmap("./utils/resources/close.png"))
        self.setIcon(self.icon)


class SendButton(QPushButton):
    def __init__(self, text, msgbox, parent=None):
        super().__init__(text, parent=parent)
        self._parent = parent
        self.msgbox = msgbox

    def minimumSizeHint(self):
        return self.sizeHint()

    def sizeHint(self):
        height = self._parent.message_text.height()
        width = 40
        return QSize(width, height)


class MessageBubble(QTextEdit):
    # append_text_signal = Signal(str)

    def __init__(self, text, viewport, role, parent=None):
        super().__init__(parent=parent)
        self.setReadOnly(True)
        self.setProperty("class", "bubble")
        self.setProperty("class", role)
        self._viewport = viewport
        self.margin = QMargins(6, 6, 6, 6)
        self._text = ''
        self.append_text(text)
        # self.append_text_signal.connect(self.append_text)

    def append_text(self, text):
        self._text += text
        self.setPlainText(self._text)
        self.setFixedSize(self.sizeHint())

    def sizeHint(self):
        metrics = QFontMetrics(self.font())
        width = self._viewport.width() * 0.8
        tb = self.margin.top() + self.margin.bottom()
        height = metrics.height() + 1
        text_width = metrics.horizontalAdvance(self._text)
        if text_width > width:
            times = math.ceil(text_width / width) + 1
            num_newlines = self._text.count('\n')
            height *= times + num_newlines
        return QSize(int(width), int(height) + tb)

    def minimumSizeHint(self):
        return self.sizeHint()


class MessageText(QTextEdit):
    enterPressed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent=parent)

    def keyPressEvent(self, event):
        # # Check if the key event is a paste shortcut (Ctrl+V or Cmd+V)
        # if event.matches(QKeySequence.Paste):
        #     self.setFixedSize(self.sizeHint())
        #     return
        #     # Get the clipboard
        #     clipboard = QApplication.clipboard()
        #     # Get the plain text from the clipboard
        #     text = clipboard.text()
        #     # Insert the plain text at the cursor position
        #     self.insertPlainText(text)
        #     self.setFixedSize(self.sizeHint())
        #     return
        # else:
        #     # If it's not a paste event, call the parent class implementation
        #     super().keyPressEvent(event)
        combo = event.keyCombination()
        key = combo.key()
        mod = combo.keyboardModifiers()
        if key == Qt.Key.Key_Enter or key == Qt.Key.Key_Return:
            if mod == Qt.KeyboardModifier.ShiftModifier:
                event.setModifiers(Qt.KeyboardModifier.NoModifier)
                return super().keyPressEvent(event)
            else:
                return self.enterPressed.emit()
        # # else adjust height if necessary
        # else:

        se = super().keyPressEvent(event)
        self.setFixedSize(self.sizeHint())
        return se

    def sizeHint(self):
        metrics = QFontMetrics(self.font())
        # width of textedit
        width = self.width()
        font_height = metrics.height()
        # text_width = metrics.horizontalAdvance(self.toPlainText())
        text_width = metrics.boundingRect(self.toPlainText()).width() * 1.1

        # times = 3
        # if text_width > width:
        num_newlines = self.toPlainText().count('\n')
        times = max(3, math.ceil(text_width / width) + num_newlines)
        # font_height *= times
        return QSize(int(width), int(font_height * times))
        # return QSize(int(width), int(font_height * (times + num_newlines)))

    files = []

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            self.files.append(url.toLocalFile())
        event.accept()


class Main(QMainWindow):
    new_bubble_signal = Signal(dict)
    new_sentence_signal = Signal(str)

    mouseEntered = Signal()
    mouseLeft = Signal()

    def __init__(self, agent=None):
        super().__init__()
        from agent.base import Agent
        self.setWindowTitle('OpenAgent')
        self.setWindowFlags(Qt.FramelessWindowHint)

        self.agent = Agent()
        # self.agent = agent
        self.chat_bubbles = []
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.central = QWidget()
        self.central.setProperty("class", "central")
        self._layout = QVBoxLayout(self.central)
        self.setMouseTracking(True)

        # self.minimizeButton = TitleBarButtonMin(parent=self)
        # self.closeButton = TitleBarButtonClose(parent=self)
        # self.button_layout = QHBoxLayout()
        # self.button_layout.addStretch(1)
        # self.button_layout.addWidget(self.minimizeButton)
        # self.button_layout.addWidget(self.closeButton)
        # self._layout.addLayout(self.button_layout, 0)
        # # make button_layout transparent background


        self._scroll = QScrollArea(self)
        self._scroll_widget = QWidget(self._scroll)
        self._scroll.setWidget(self._scroll_widget)
        self._scroll.setWidgetResizable(True)
        self._scroll_layout = QVBoxLayout(self._scroll_widget)
        self._scroll_layout.addStretch(1)
        self.is_expanded = False
        self._layout.addWidget(self._scroll)
        self.message_text = MessageText()
        self.send_button = SendButton("Send", self.message_text, self)
        hlayout = QHBoxLayout()
        hlayout.addWidget(self.message_text)
        hlayout.addWidget(self.send_button)
        self.message_text.setFixedHeight(65)
        self.message_text.setProperty("class", "msgbox")
        self.send_button.setProperty("class", "send")
        self.spacer = QSpacerItem(0, 0)
        hlayout.setSpacing(0)
        self._layout.setSpacing(1)
        self._layout.addLayout(hlayout)
        self.setCentralWidget(self.central)
        self.send_button.clicked.connect(self.on_button_click)
        self.message_text.enterPressed.connect(self.on_button_click)

        self.new_bubble_signal.connect(self.insert_bubble)
        self.new_sentence_signal.connect(self.new_sentence)
        self.last_assistant_bubble = None

    @Slot(str)
    def new_sentence(self, sentence):
        if self.last_assistant_bubble is None:
            self.new_bubble_signal.emit({'id': -1, 'role': 'assistant', 'content': sentence})
        else:
            self.last_assistant_bubble.append_text(sentence)
            self._scroll.verticalScrollBar().setValue(self._scroll.verticalScrollBar().maximum())
            QApplication.processEvents()
        # self._scroll.verticalScrollBar().setValue(self._scroll.verticalScrollBar().maximum())
        # QApplication.processEvents()

    def mousePressEvent(self, event):
        self.oldPosition = event.globalPos()

    def mouseMoveEvent(self, event):
        delta = QPoint(event.globalPos() - self.oldPosition)
        self.move(self.x() + delta.x(), self.y() + delta.y())
        self.oldPosition = event.globalPos()

    def toggle_expand(self):
        self.is_expanded = not self.is_expanded
        if self.is_expanded:
            self.change_height(750)
            self._scroll.show()
            # self.titleBar.show()
        else:
            self._scroll.hide()
            self.change_height(100)
            # self.titleBar.hide()

    def on_button_click(self):
        self.send_message()

    def enterEvent(self, event):
        self.mouseEntered.emit()
        self.toggle_expand()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.mouseLeft.emit()
        self.toggle_expand()
        super().leaveEvent(event)

    def change_height(self, height):
        old_height = self.height()
        self.move(self.x(), self.y() - (height - old_height))
        self.setFixedHeight(height)

    def resizeEvent(self, event):
        app = QCoreApplication.instance()  # / #
        screen = app.primaryScreen()
        screenwidth = screen.size().width()
        screenheight = screen.size().height()
        # get bottom right screen coords
        # pady = 10
        # padx = BOTTOM_CORNER_X
        width = self.size().width()
        height = self.size().height()
        x = screenwidth - width #- padx
        y = screenheight - height #- pady
        self.move(x, y)
        super().resizeEvent(event)

    def sizeHint(self):
        return QSize(300, 100)

    @Slot(dict)
    def insert_bubble(self, message=None):
        # REMOVE BUBBLES FOR REMOVED MESSAGES - todo
        # if message is None:
        #     message = self.message_text.toPlainText()
        # if message['role'] == 'user':
        #     self.message_text.clear()
        viewport = self._scroll
        bubble = MessageBubble(message['content'], viewport, role=message['role'])
        self.chat_bubbles.append(bubble)
        count = len(self.chat_bubbles)
        self.last_assistant_bubble = bubble if message['role'] == 'assistant' else None

        self._scroll_layout.insertWidget(count - 1, bubble)

        self.setFixedSize(self.sizeHint())
        self._scroll.verticalScrollBar().setValue(self._scroll.verticalScrollBar().maximum())
        QApplication.processEvents()

        return bubble

    def send_message(self):
        message = self.message_text.toPlainText()
        if message == '':
            return
        if self.agent.context.message_history.last_role() == 'user':
            last = self.agent.context.message_history.last()
            new_msg = Message(msg_id=last['id'], content=last['content'], role='user')   # todo - cleanup
        else:
            new_msg = self.agent.save_message('user', message)

        if not new_msg:
            return

        QTimer.singleShot(1, self.message_text.clear)
        self.new_bubble_signal.emit({'id': new_msg.id, 'role': 'user', 'content': new_msg.content})
        self._scroll.verticalScrollBar().setValue(self._scroll.verticalScrollBar().maximum())
        QApplication.processEvents()


        # # first known msg  # todo remove deleted messages
        # if len(self.agent.context.message_history._messages) > 0:
        #     first_id = self.agent.context.message_history._messages[0].id
        #     # remove removed bubbles
        #     for bubble_id in list(self.chat_bubbles.keys()):
        #         if bubble_id < first_id:
        #             bubble = self.chat_bubbles[bubble_id]
        #             self._scroll_layout.removeWidget(bubble)
        #             self.chat_bubbles.pop(bubble_id)

        for sentence in self.agent.receive(stream=True):
            self.new_sentence_signal.emit(sentence)


class GUI:
    def __init__(self):
        self.agent = None

    def run(self):
        # Check if the database is available
        if not check_database():
            # If not, show a QFileDialog to get the database location
            database_location, _ = QFileDialog.getOpenFileName(None, "Open Database", "", "Database Files (*.db);;All Files (*)")

            if not database_location:
                QMessageBox.critical(None, "Error", "Database not selected. Application will exit.")
                return

            # Set the database location in the agent
            config.set_value('system.db-path', database_location)

        app = QApplication(sys.argv)
        app.setStyleSheet(STYLE)
        m = Main()  # self.agent)
        msgs = m.agent.context.message_history.get(msg_limit=30, pad_consecutive=False, only_role_content=False)
        m.show()
        for msg in msgs:
            m.insert_bubble(msg)

        app.exec()