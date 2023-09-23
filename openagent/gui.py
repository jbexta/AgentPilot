import sys
import math

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
# import open
# import oa
from agent.base import Agent

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
        self.minimizeButton = TitleBarButtonMin(parent=self)
        self.closeButton = TitleBarButtonClose(parent=self)
        sizePolicy = QSizePolicy()
        sizePolicy.setHorizontalPolicy(QSizePolicy.Policy.Fixed)
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
    def __init__(self, text, viewport, role, parent=None):
        super().__init__(parent=parent)
        self.setReadOnly(True)
        self.setProperty("class", "bubble")
        self.setProperty("class", role)
        self._viewport = viewport
        self.margin = QMargins(6, 6, 6, 6)
        self._text = ''
        self.append_text(text)

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
        self.setFixedSize(self.sizeHint())
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

        return super().keyPressEvent(event)

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
    mouseEntered = Signal()
    mouseLeft = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle('OpenAgent')
        self.setWindowFlags(Qt.FramelessWindowHint)

        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.central = QWidget()
        self.central.setProperty("class", "central")
        self._layout = QVBoxLayout(self.central)
        self.titleBar = TitleBar(self)
        self.setMouseTracking(True)
        self._layout.addWidget(self.titleBar)
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
        self.titleBar.closeButton.closeApp.connect(self.close)
    #     self.response_timer = QTimer()
    #     self.response_timer.timeout.connect(self.send_response)
    #     self.message_text.enterPressed.connect(self.send_response)
    #     self.send_button.clicked.connect(self.send_response)
    #     self.response_index = 0
    #     self.responses = [
    #         "World? Who the heck is World?",
    #         "My name is Roger, definitely not World.",
    #         "Too Late!",
    #     ]

    # def send_response(self):
    #     if self.response_index < len(self.responses):
    #         message = self.responses[self.response_index]
    #         QTimer.singleShot(
    #             900, lambda: self.send_message(message=message, prop="receiver")
    #         )
    #         self.response_index += 1

    def mousePressEvent(self, event):
        self.oldPosition = event.globalPos()


    def mouseMoveEvent(self, event):
        delta = QPoint(event.globalPos() - self.oldPosition)
        self.move(self.x() + delta.x(), self.y() + delta.y())
        self.oldPosition = event.globalPos()


    def toggle_expand(self):
        self.is_expanded = True  # not self.is_expanded
        if self.is_expanded:
            self.change_height(750)
            self._scroll.show()
            self.titleBar.show()
        else:
            self._scroll.hide()
            self.change_height(100)
            self.titleBar.hide()

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
        screen = app.primaryScreen()
        screenwidth = screen.size().width()
        screenheight = screen.size().height()
        pady = BOTTOM_CORNER_Y
        padx = BOTTOM_CORNER_X
        width = self.size().width()
        height = self.size().height()
        x = screenwidth - width - padx
        y = screenheight - height - pady
        self.move(x, y)
        super().resizeEvent(event)

    def sizeHint(self):
        return QSize(300, 100)

    def insert_bubble(self, message=None):
        # if message is None:
        #     message = self.message_text.toPlainText()
        if message['role'] == 'user':
            self.message_text.clear()
        viewport = self._scroll
        bubble = MessageBubble(message['content'], viewport, role=message['role'])
        count = self._scroll_layout.count()
        self._scroll_layout.insertWidget(count - 1, bubble)
        chat_bubbles[message['id']] = bubble

        self._scroll.verticalScrollBar().setValue(self._scroll.verticalScrollBar().maximum())
        app.processEvents()

        return bubble
        # self.message_text.clear()

        # for sentence in agent.send_and_stream(message):
        #     bubble
    def send_message(self):
        message = self.message_text.toPlainText()
        if message == '': return
        if agent.context.message_history.last_role() == 'user': return

        new_msg = agent.save_message('user', message)
        if not new_msg: return

        self.insert_bubble({'id': new_msg.id, 'role': 'user', 'content': new_msg.content})

        assistant_bubble = None
        for sentence in agent.receive(message, stream=True):
            if assistant_bubble is None:
                assistant_bubble = self.insert_bubble({'id': -1, 'role': 'assistant', 'content': sentence})
                continue
            else:
                assistant_bubble.append_text(sentence)


chat_bubbles = {}

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    m = Main()

    m.show()

    agent = Agent()
    msgs = agent.context.message_history.get(msg_limit=30, pad_consecutive=False, only_role_content=False)
    for msg in msgs:
        m.insert_bubble(msg)
    app.exec()

