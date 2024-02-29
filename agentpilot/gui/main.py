
import os
import sys

from PySide6.QtWidgets import *
from PySide6.QtCore import Signal, QSize, QTimer, QMimeData, QPoint, QTranslator, QLocale
from PySide6.QtGui import QPixmap, QIcon, QFont, QTextCursor, QTextDocument, QFontMetrics, QGuiApplication, Qt, QCursor

from agentpilot.utils.sql_upgrade import upgrade_script, versions
from agentpilot.utils import sql, api, resources_rc
from agentpilot.system.base import SystemManager

import logging

from agentpilot.gui.pages.chat import Page_Chat
from agentpilot.gui.pages.settings import Page_Settings
from agentpilot.gui.pages.agents import Page_Agents
from agentpilot.gui.pages.contexts import Page_Contexts
from agentpilot.utils.helpers import display_messagebox
from agentpilot.gui.style import get_stylesheet
from agentpilot.gui.components.config import ConfigTree, CVBoxLayout, CHBoxLayout
from agentpilot.gui.widgets.base import IconButton, colorize_pixmap

logging.basicConfig(level=logging.DEBUG)

os.environ["QT_OPENGL"] = "software"


BOTTOM_CORNER_X = 400
BOTTOM_CORNER_Y = 450

PIN_MODE = True


class TitleButtonBar(QWidget):
    def __init__(self, parent):
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

    class TitleBarButtonPin(IconButton):
        def __init__(self, parent):
            super().__init__(parent=parent, icon_path=":/resources/icon-pin-on.png", size=20, opacity=0.7)
            self.clicked.connect(self.toggle_pin)

        def toggle_pin(self):
            global PIN_MODE
            PIN_MODE = not PIN_MODE
            icon_iden = "on" if PIN_MODE else "off"
            icon_file = f":/resources/icon-pin-{icon_iden}.png"
            self.setIconPixmap(QPixmap(icon_file))

    class TitleBarButtonMin(IconButton):
        def __init__(self, parent):
            super().__init__(parent=parent, icon_path=":/resources/minus.png", size=20, opacity=0.7)
            self.clicked.connect(self.window_action)

        def window_action(self):
            self.parent.main.collapse()
            if self.window().isMinimized():
                self.window().showNormal()
            else:
                self.window().showMinimized()

    class TitleBarButtonClose(IconButton):

        def __init__(self, parent):
            super().__init__(parent=parent, icon_path=":/resources/close.png", size=20, opacity=0.7)
            self.clicked.connect(self.closeApp)

        def closeApp(self):
            self.window().close()


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
        self.layout.setSpacing(5)
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
        icon_pixmap = QPixmap(f":/resources/icon-{icon_iden}.png")
        self.btn_new_context.setIconPixmap(icon_pixmap)

    class SideBar_NewContext(IconButton):
        def __init__(self, parent):
            super().__init__(parent=parent, icon_path=":/resources/icon-new-large.png", size=50, opacity=0.7,
                             tooltip="New context", icon_size_percent=0.85)
            self.main = parent.main
            self.clicked.connect(self.on_clicked)

            self.setCheckable(True)
            self.setObjectName("homebutton")

        def on_clicked(self):
            is_current_widget = self.main.content.currentWidget() == self.main.page_chat
            if is_current_widget:
                copy_context_id = self.main.page_chat.workflow.id
                self.main.page_chat.new_context(copy_context_id=copy_context_id)
            else:
                self.main.content.setCurrentWidget(self.main.page_chat)

    class SideBar_Settings(IconButton):
        def __init__(self, parent):
            super().__init__(parent=parent, icon_path=":/resources/icon-settings.png", size=50, opacity=0.7,
                             tooltip="Settings", icon_size_percent=0.85)
            self.main = parent.main
            self.clicked.connect(self.on_clicked)
            self.setCheckable(True)

        def on_clicked(self):
            self.main.content.setCurrentWidget(self.main.page_settings)

    class SideBar_Agents(IconButton):
        def __init__(self, parent):
            super().__init__(parent=parent, icon_path=":/resources/icon-agent.png", size=50, opacity=0.7,
                             tooltip="Agents", icon_size_percent=0.85)
            self.main = parent.main
            self.clicked.connect(self.on_clicked)
            self.setCheckable(True)

        def on_clicked(self):
            self.main.content.setCurrentWidget(self.main.page_agents)

    class SideBar_Contexts(IconButton):
        def __init__(self, parent):
            super().__init__(parent=parent, icon_path=":/resources/icon-contexts.png", size=50, opacity=0.7,
                             tooltip="Contexts", icon_size_percent=0.85)
            self.main = parent.main
            self.clicked.connect(self.on_clicked)
            self.setCheckable(True)

        def on_clicked(self):
            self.main.content.setCurrentWidget(self.main.page_contexts)


class MicButton(IconButton):
    def __init__(self, parent):
        super().__init__(parent=parent, icon_path=':/resources/icon-mic.png', size=20)
        self.setProperty("class", "send")
        self.move(self.parent.width() - 66, 12)
        self.hide()
        self.clicked.connect(self.on_clicked)
        self.recording = False

    def on_clicked(self):
        pass


class MessageText(QTextEdit):
    enterPressed = Signal()

    def __init__(self, parent):
        super().__init__(parent=None)
        self.parent = parent
        # self.setCursor(QCursor(Qt.PointingHandCursor))

        self.mic_button = MicButton(self)

        conf = self.parent.system.config.dict
        text_size = conf.get('display.text_size', 15)
        text_font = conf.get('display.text_font', '')

        self.font = QFont()
        if text_font != '':
            self.font.setFamily(text_font)
        self.font.setPointSize(text_size)
        self.setFont(self.font)
        self.setAcceptDrops(True)

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
                return  # se
            else:
                if self.toPlainText().strip() == '':
                    return

                # If context not responding
                if not self.parent.page_chat.workflow.responding:
                    self.enterPressed.emit()
                    return

        se = super().keyPressEvent(event)
        self.setFixedSize(self.sizeHint())
        self.parent.sync_send_button_size()
        return  # se

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

    # mouse hover event show mic button
    def enterEvent(self, event):
        self.mic_button.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.mic_button.hide()
        super().leaveEvent(event)

    # def dragEnterEvent(self, event):
    #     logging.debug('MessageText.dragEnterEvent()')
    #     if event.mimeData().hasUrls():
    #         event.accept()
    #     else:
    #         event.ignore()
    #
    # def dropEvent(self, event):
    #     logging.debug('MessageText.dropEvent()')
    #     for url in event.mimeData().urls():
    #         self.files.append(url.toLocalFile())
    #         # insert text where cursor is
    #
    #     event.accept()
    #
    # def insertFromMimeData(self, source: QMimeData):
    #     """
    #     Reimplemented from QTextEdit.insertFromMimeData().
    #     Inserts plain text data from the MIME data source.
    #     """
    #     # Check if the MIME data source has text
    #     if source.hasText():
    #         # Get the plain text from the source
    #         text = source.text()
    #
    #         # Insert the plain text at the current cursor position
    #         self.insertPlainText(text)
    #     else:
    #         # If the source does not contain text, call the base class implementation
    #         super().insertFromMimeData(source)


class SendButton(IconButton):
    def __init__(self, parent):  # msgbox,
        super().__init__(parent=parent, icon_path=":/resources/icon-send.png")
        self.parent = parent
        # self.msgbox = msgbox
        self.setFixedSize(70, 46)
        self.setProperty("class", "send")
        self.update_icon(is_generating=False)

    def update_icon(self, is_generating):
        icon_iden = 'send' if not is_generating else 'stop'
        pixmap = colorize_pixmap(QPixmap(f":/resources/icon-{icon_iden}.png"))
        self.setIconPixmap(pixmap)

    def minimumSizeHint(self):
        return self.sizeHint()

    def sizeHint(self):
        height = self.parent.message_text.height()
        width = 70
        return QSize(width, height)


class Main(QMainWindow):
    # new_bubble_signal = Signal(dict)
    new_sentence_signal = Signal(int, str)
    finished_signal = Signal()
    error_occurred = Signal(str)
    title_update_signal = Signal(str)

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

    def apply_stylesheet(self):
        QApplication.instance().setStyleSheet(get_stylesheet(self.system))

        # pixmaps
        for child in self.findChildren(IconButton):
            child.setIconPixmap()
        # trees
        for child in self.findChildren(QTreeWidget):
            child.apply_stylesheet()

        text_color = self.system.config.dict.get('display.text_color', '#c4c4c4')
        self.page_chat.topbar.title_label.setStyleSheet(f"QLineEdit {{ color: #E6{text_color.replace('#', '')}; background-color: transparent; }}"
                                           f"QLineEdit:hover {{ color: {text_color}; }}")
        # # text edits
        # for child in self.findChildren(QTextEdit):
        #     child.apply_stylesheet()

    def __init__(self, system):  # , base_agent=None):
        super().__init__()

        screenrect = QApplication.primaryScreen().availableGeometry()
        self.move(screenrect.right() - self.width(), screenrect.bottom() - self.height())

        # Check if the database is ok
        self.check_db()

        api.load_api_keys()

        self.system = system  # SystemManager()

        # self.toggle_always_on_top(first_load=True)
        always_on_top = self.system.config.dict.get('system.always_on_top', True)
        current_flags = self.windowFlags()
        new_flags = current_flags
        if always_on_top:
            new_flags |= Qt.WindowStaysOnTopHint
        else:
            new_flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(new_flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)

        self.leave_timer = QTimer(self)
        self.leave_timer.setSingleShot(True)
        self.leave_timer.timeout.connect(self.collapse)

        self.setWindowTitle('AgentPilot')

        # always_on_top = self.system.config.dict.get('system.always_on_top', True)
        # self.setWindowFlags(Qt.FramelessWindowHint)

        self.setWindowIcon(QIcon(':/resources/icon.png'))
        # self.toggle_always_on_top()
        self.central = QWidget()
        self.central.setProperty("class", "central")
        self._layout = QVBoxLayout(self.central)
        self._layout.setSpacing(6)
        self._layout.setContentsMargins(8, 8, 8, 8)

        self.setMouseTracking(True)
        self.setAcceptDrops(True)

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
        self.content.setMinimumWidth(600)

        # Horizontal layout for content and sidebar
        self.content_container = QWidget()
        hlayout = CHBoxLayout(self.content_container)
        hlayout.addWidget(self.content)
        hlayout.addWidget(self.sidebar)

        self._layout.addWidget(self.content_container)

        # Message text and send button
        self.message_text = MessageText(self)
        self.message_text.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.message_text.setFixedHeight(46)
        self.message_text.setProperty("class", "msgbox")
        self.send_button = SendButton(self)

        # Horizontal layout for message text and send button
        self.input_container = QWidget()
        hlayout = CHBoxLayout(self.input_container)
        hlayout.addWidget(self.message_text)
        hlayout.addWidget(self.send_button)

        self._layout.addWidget(self.input_container)
        # self._layout.setSpacing(1)

        self.setCentralWidget(self.central)

        self.send_button.clicked.connect(self.page_chat.on_button_click)
        self.message_text.enterPressed.connect(self.page_chat.on_button_click)

        # self.new_bubble_signal.connect(self.page_chat.insert_bubble, Qt.QueuedConnection)
        self.new_sentence_signal.connect(self.page_chat.new_sentence, Qt.QueuedConnection)
        self.finished_signal.connect(self.page_chat.on_receive_finished, Qt.QueuedConnection)
        self.error_occurred.connect(self.page_chat.on_error_occurred, Qt.QueuedConnection)
        self.title_update_signal.connect(self.page_chat.on_title_update, Qt.QueuedConnection)
        self.oldPosition = None
        self.expanded = False

        self.show()
        self.page_chat.load()
        self.page_settings.pages['System'].toggle_dev_mode()

        app_config = self.system.config.dict
        self.page_settings.load_config(app_config)

        self.sidebar.btn_new_context.setFocus()
        self.activateWindow()

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
        global PIN_MODE
        if PIN_MODE:
            return
        if not self.expanded:
            return

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

    def toggle_always_on_top(self):
        # # self.hide()
        always_on_top = self.system.config.dict.get('system.always_on_top', True)
        # self.setWindowFlag(Qt.WindowStaysOnTopHint, always_on_top)
        # self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Ensure any other window flags you want to keep are preserved
        current_flags = self.windowFlags()
        new_flags = current_flags

        # Set or unset the always-on-top flag depending on the setting
        if always_on_top:
            new_flags |= Qt.WindowStaysOnTopHint
        else:
            new_flags &= ~Qt.WindowStaysOnTopHint

        # Hide the window before applying new flags
        self.hide()
        # Apply the new window flags
        self.setWindowFlags(new_flags)

        # Ensuring window borders and transparency
        self.setAttribute(Qt.WA_TranslucentBackground)  # Maintain transparency
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)  # Keep it frameless
        self.show()

    def mousePressEvent(self, event):
        logging.debug(f'Main.mousePressEvent: {event}')
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
        logging.debug(f'Main.change_height({height})')
        old_height = self.height()
        self.setFixedHeight(height)
        self.move(self.x(), self.y() - (height - old_height))

    def change_width(self, width):
        logging.debug(f'Main.change_width({width})')
        old_width = self.width()
        self.setFixedWidth(width)
        self.move(self.x() - (width - old_width), self.y())

    def sizeHint(self):
        logging.debug('Main.sizeHint()')
        return QSize(600, 100)

    def load_page(self, index):
        logging.debug(f'Main.load_page({index})')
        self.sidebar.update_buttons()
        self.content.widget(index).load()

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
        self.page_chat.attachment_bar.add_attachments(paths=paths)
        event.acceptProposedAction()


def launch():
    try:
        system = SystemManager()
        app = QApplication(sys.argv)
        app.setStyleSheet(get_stylesheet(system=system))

        locale = QLocale.system().name()
        translator = QTranslator()
        if translator.load(':/lang/es.qm'):  # + QLocale.system().name()):
            app.installTranslator(translator)

        m = Main(system=system)
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
