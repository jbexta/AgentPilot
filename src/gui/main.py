import asyncio
import os
import sys
import uuid
from collections import Counter
from functools import partial

import nest_asyncio
from PySide6.QtWidgets import *
from PySide6.QtCore import Signal, QSize, QTimer, QPoint, Slot, QRunnable, QEvent, QThreadPool
from PySide6.QtGui import QPixmap, QIcon, QFont, QTextCursor, QTextDocument, QFontMetrics, QGuiApplication, Qt, \
    QPainter, QColor, QKeyEvent, QCursor

from src.gui.pages.blocks import Page_Block_Settings
from src.gui.pages.tools import Page_Tool_Settings
from src.utils.sql_upgrade import upgrade_script
from src.utils import sql, telemetry
from src.system.base import manager

import logging

from src.gui.pages.chat import Page_Chat
from src.gui.pages.settings import Page_Settings
from src.gui.pages.agents import Page_Entities
from src.gui.pages.contexts import Page_Contexts
from src.utils.helpers import display_messagebox, apply_alpha_to_hex
from src.gui.style import get_stylesheet
from src.gui.config import CVBoxLayout, CHBoxLayout, ConfigPages
from src.gui.widgets import IconButton, colorize_pixmap, find_main_widget

logging.basicConfig(level=logging.DEBUG)

os.environ["QT_OPENGL"] = "software"

nest_asyncio.apply()

BOTTOM_CORNER_X = 400
BOTTOM_CORNER_Y = 450

PIN_MODE = True


class TOSDialog(QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Terms of Use")
        self.setWindowIcon(QIcon(':/resources/icon.png'))
        self.setMinimumSize(300, 350)
        self.resize(300, 350)

        self.setWindowFlags(Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowCloseButtonHint)

        layout = QVBoxLayout(self)

        self.tos_label = QTextEdit("""
The material embodied in this software is provided to you "as-is" and without warranty of any kind, express, implied or otherwise, including without limitation, any warranty of fitness for a particular purpose. 
In no event shall Agent Pilot or it's creators be liable to you or anyone else for any direct, special, incidental, indirect or consequential damages of any kind, or any damages whatsoever, including but not limited to, loss of profit, loss of use, savings or revenue, or the claims of third parties, whether or not Agent Pilot creators have been advised of the possibility of such loss, however caused and on any theory of liability, arising out of or in connection with the possession, use or performance of this software.
"""
                                )
        self.tos_label.setReadOnly(True)
        self.tos_label.setFrameStyle(QFrame.NoFrame)

        layout.addWidget(self.tos_label)

        h_layout = QHBoxLayout()
        h_layout.addStretch(1)

        self.decline_button = QPushButton("Decline")
        self.decline_button.setFixedWidth(100)
        self.decline_button.clicked.connect(self.reject)
        h_layout.addWidget(self.decline_button)

        self.agree_button = QPushButton("Agree")
        self.agree_button.setFixedWidth(100)
        self.agree_button.clicked.connect(self.accept)
        h_layout.addWidget(self.agree_button)

        layout.addLayout(h_layout)


class TitleButtonBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.parent = parent
        self.main = parent.main
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(20)

        self.btn_minimise = IconButton(parent=self, icon_path=":/resources/minus.png", size=20, opacity=0.7)
        self.btn_pin = IconButton(parent=self, icon_path=":/resources/icon-pin-on.png", size=20, opacity=0.7)
        self.btn_close = IconButton(parent=self, icon_path=":/resources/close.png", size=20, opacity=0.7)
        self.btn_minimise.clicked.connect(self.window_action)
        self.btn_pin.clicked.connect(self.toggle_pin)
        self.btn_close.clicked.connect(self.closeApp)

        self.layout = CHBoxLayout(self)
        self.layout.addStretch(1)
        self.layout.addWidget(self.btn_minimise)
        self.layout.addWidget(self.btn_pin)
        self.layout.addWidget(self.btn_close)

        self.setMouseTracking(True)

    def toggle_pin(self):
        global PIN_MODE
        PIN_MODE = not PIN_MODE
        icon_iden = "on" if PIN_MODE else "off"
        icon_file = f":/resources/icon-pin-{icon_iden}.png"
        self.btn_pin.setIconPixmap(QPixmap(icon_file))

    def window_action(self):
        self.parent.main.collapse()
        if self.window().isMinimized():
            self.window().showNormal()
        else:
            self.window().showMinimized()

    def closeApp(self):
        self.window().close()


class MainPages(ConfigPages):
    def __init__(self, parent):
        super().__init__(
            parent=parent,
            right_to_left=True,
            bottom_to_top=True,
            default_page='Chat',
            button_kwargs=dict(
                button_type='icon',
                icon_size=50
            ),
            is_pin_transmitter=True,
        )  # , align_left=)
        self.main = parent
        self.pages = {
            'Settings': Page_Settings(parent),
            'Tools': Page_Tool_Settings(parent),
            'Blocks': Page_Block_Settings(parent),
            'Agents': Page_Entities(parent),
            'Contexts': Page_Contexts(parent),
            'Chat': Page_Chat(parent),
        }
        self.pinnable_pages = ['Blocks', 'Tools']
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # self.hidden_pages = ['Settings']
        self.build_schema()
        self.title_bar = TitleButtonBar(parent=self)
        self.settings_sidebar.layout.insertWidget(0, self.title_bar)
        self.settings_sidebar.setFixedWidth(70)
        self.settings_sidebar.setContentsMargins(4,0,0,4)

    def load(self):
        super().load()

        current_page_is_chat = self.content.currentWidget() == self.pages['Chat']
        icon_iden = 'chat' if not current_page_is_chat else 'new-large'
        icon_pixmap = QPixmap(f":/resources/icon-{icon_iden}.png")
        if self.settings_sidebar:
            self.settings_sidebar.page_buttons['Chat'].setIconPixmap(icon_pixmap)


class MessageButtonBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.parent = parent
        self.mic_button = self.MicButton(self)
        self.enhance_button = self.EnhanceButton(self)
        self.layout = CVBoxLayout(self)
        self.layout.addWidget(self.mic_button)
        self.layout.addWidget(self.enhance_button)
        self.hide()

    class MicButton(IconButton):
        def __init__(self, parent):
            super().__init__(parent=parent, icon_path=':/resources/icon-mic.png', size=20, opacity=0.75)
            self.setProperty("class", "send")
            self.clicked.connect(self.on_clicked)
            self.recording = False

        def on_clicked(self):
            pass

    class EnhanceButton(IconButton):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                icon_path=':/resources/icon-wand.png',
                size=20,
                opacity=0.75,
                tooltip='Enhance the text using a Metaprompt block.'
            )
            self.setProperty("class", "send")
            self.main = find_main_widget(self)
            self.clicked.connect(self.on_clicked)
            self.enhancing_text = ''
            self.metaprompt_blocks = {}

        @Slot(str)
        def on_new_enhanced_sentence(self, chunk):
            current_text = self.main.message_text.toPlainText()
            self.main.message_text.setPlainText(current_text + chunk)
            self.main.message_text.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key.Key_End, Qt.KeyboardModifier.NoModifier))
            self.main.message_text.verticalScrollBar().setValue(self.main.message_text.verticalScrollBar().maximum())

        @Slot(str)
        def on_enhancement_error(self, error_message):
            self.main.message_text.setPlainText(self.enhancing_text)
            self.enhancing_text = ''
            display_messagebox(
                icon=QMessageBox.Warning,
                title="Enhancement error",
                text=f"An error occurred while enhancing the text: {error_message}",
                buttons=QMessageBox.Ok
            )

        def on_clicked(self):
            self.metaprompt_blocks = {k: v for k, v in self.main.system.blocks.to_dict().items() if v.get('block_type', '') == 'Metaprompt'}
            # if len(self.metaprompt_blocks) > 1:
                # show a context menu with all available metaprompt blocks
            if len(self.metaprompt_blocks) == 0:
                display_messagebox(
                    icon=QMessageBox.Warning,
                    title="No Metaprompt blocks found",
                    text="No Metaprompt blocks found, create them in the blocks page.",
                    buttons=QMessageBox.Ok
                )
                return

            messagebox_input = self.main.message_text.toPlainText().strip()
            if messagebox_input == '':
                display_messagebox(
                    icon=QMessageBox.Warning,
                    title="No message found",
                    text="Type a message in the message box to enhance.",
                    buttons=QMessageBox.Ok
                )
                return

            menu = QMenu(self)
            for name in self.metaprompt_blocks.keys():
                action = menu.addAction(name)
                action.triggered.connect(partial(self.on_metaprompt_selected, name))

            menu.exec_(QCursor.pos())

        def on_metaprompt_selected(self, metablock_name):
            self.run_metaprompt(metablock_name)

        def run_metaprompt(self, metablock_name):
            metablock_text = self.metaprompt_blocks[metablock_name].get('data', '')
            metablock_model = self.metaprompt_blocks[metablock_name].get('prompt_model', '')
            messagebox_input = self.main.message_text.toPlainText().strip()

            if '{{INPUT}}' not in metablock_text:
                ret_val = display_messagebox(
                    icon=QMessageBox.Warning,
                    title="No {{INPUT}} found",
                    text="The Metaprompt block should contain '{{INPUT}}' to be able to enhance the text.",
                    buttons=QMessageBox.Ok | QMessageBox.Cancel
                )
                if ret_val != QMessageBox.Ok:
                    return

            metablock_text = metablock_text.replace('{{INPUT}}', messagebox_input)

            self.enhancing_text = self.main.message_text.toPlainText()
            self.main.message_text.clear()
            enhance_runnable = self.EnhancementRunnable(self, metablock_model, metablock_text)
            self.main.threadpool.start(enhance_runnable)

        class EnhancementRunnable(QRunnable):
            def __init__(self, parent, metablock_model, metablock_text):
                super().__init__()
                # self.parent = parent
                self.main = parent.main
                self.metablock_model = metablock_model
                self.metablock_text = metablock_text

            def run(self):
                try:
                    asyncio.run(self.enhance_text(self.metablock_model, self.metablock_text))
                except Exception as e:
                    self.main.enhancement_error_occurred.emit(str(e))

            async def enhance_text(self, model, metablock_text):
                stream = await self.main.system.providers.run_model(
                    model_obj=model,
                    messages=[{'role': 'user', 'content': metablock_text}],
                )

                async for resp in stream:
                    delta = resp.choices[0].get('delta', {})
                    if not delta:
                        continue
                    content = delta.get('content', '')
                    self.main.new_enhanced_sentence_signal.emit(content)

class Overlay(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.suggested_text = ''

    def set_suggested_text(self, text):
        self.suggested_text = text
        self.update()

    def paintEvent(self, event):
        if not self.suggested_text:
            return

        conf = self.editor.parent.system.config.dict
        text_size = int(conf.get('display.text_size', 15) * 0.6)
        text_font = conf.get('display.text_font', '')

        painter = QPainter(self)
        painter.setPen(QColor(128, 128, 128))  # Set grey color for the suggestion text

        font = self.editor.font
        font.setPointSize(text_size)
        font_metrics = QFontMetrics(font)
        cursor_rect = self.editor.cursorRect()
        x = cursor_rect.right()
        y = cursor_rect.top()

        painter.setFont(font)

        painter.drawText(x, y + font_metrics.ascent() + 2, self.suggested_text)


class MessageText(QTextEdit):
    enterPressed = Signal()

    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.setFixedHeight(46)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setProperty("class", "msgbox")

        self.button_bar = MessageButtonBar(self)
        self.button_bar.setFixedHeight(46)
        self.button_bar.move(self.width() - 40, 0)
        # self.mic_button = MicButton(self)
        # self.enhance_button = IconButton(parent=self, icon_path=':/resources/icon-run.png', size=20)
        # self.enhance_button.setProperty("class", "send")
        # # send_btn_width = 64
        # self.mic_button.move(self.width() - 40, 0)
        # self.enhance_button.move(self.width() - 40, self.mic_button.height())

        conf = self.parent.system.config.dict
        text_size = conf.get('display.text_size', 15)
        text_font = conf.get('display.text_font', '')

        self.font = QFont()
        if text_font != '':  #  and text_font != 'Default':
            self.font.setFamily(text_font)
        self.font.setPointSize(text_size)
        self.setFont(self.font)
        self.setAcceptDrops(True)

        self.last_continuation = ''
        self.overlay = Overlay(self)

    def update_overlay(self, suggested_continuation):
        # Position the overlay correctly
        self.overlay.setGeometry(self.contentsRect())
        # Set the suggested text for the overlay
        self.overlay.set_suggested_text(suggested_continuation)

    def keyPressEvent(self, event):
        combo = event.keyCombination()
        key = combo.key()
        mod = combo.keyboardModifiers()

        suggested_continuation = self.overlay.suggested_text
        if suggested_continuation:
            # if tab is pressed and no modifier is pressed
            if key == Qt.Key.Key_Tab and mod == Qt.KeyboardModifier.NoModifier:
                cursor = self.textCursor()
                cursor.insertText(suggested_continuation)
                self.overlay.set_suggested_text('')
                self.setFixedSize(self.sizeHint())
                self.parent.sync_send_button_size()
                return

            # If right arrow key is pressed and no modifier is pressed
            if key == Qt.Key.Key_Right and mod == Qt.KeyboardModifier.NoModifier:
                # If cursor is at the end of the text
                if self.textCursor().atEnd():
                    insert_char = suggested_continuation[0]
                    cursor = self.textCursor()
                    cursor.insertText(insert_char)
                    self.overlay.set_suggested_text(suggested_continuation[1:])
                    self.setFixedSize(self.sizeHint())
                    self.parent.sync_send_button_size()
                    return

        # Check for Ctrl + B key combination
        if key == Qt.Key.Key_B and mod == Qt.KeyboardModifier.ControlModifier:
            # Insert the code block where the cursor is
            cursor = self.textCursor()
            cursor.insertText("```\n\n```")  # Inserting with new lines between to create a space for the code
            cursor.movePosition(QTextCursor.PreviousBlock, QTextCursor.MoveAnchor,
                                1)  # Move cursor inside the code block
            self.setTextCursor(cursor)
            self.setFixedSize(self.sizeHint())  #!!#
            self.parent.sync_send_button_size()
            return  # We handle the event, no need to pass it to the base class

        if key == Qt.Key.Key_Enter or key == Qt.Key.Key_Return:
            if mod == Qt.KeyboardModifier.ShiftModifier:
                event.setModifiers(Qt.KeyboardModifier.NoModifier)

                se = super().keyPressEvent(event)
                # self.setFixedSize(self.sizeHint())
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
        continuation = self.auto_complete()
        if continuation:
            self.last_continuation = continuation
        else:
            lower_text = self.toPlainText().lower()
            # check if last continuation starts with lower_text
            if lower_text and self.last_continuation.lower().startswith(lower_text):
                continuation = self.last_continuation[len(lower_text):]
            else:
                self.overlay.set_suggested_text('')

        self.update_overlay(continuation)
        if continuation != '':
            print(f"Suggested continuation: '{continuation}'")

    def auto_complete(self):
        conf = self.parent.system.config.dict
        if not conf.get('system.auto_complete', True):
            return ''
        lower_text = self.toPlainText().lower()
        if lower_text == '':
            return ''
        all_messages = sql.get_results("""
            SELECT msg 
            FROM contexts_messages 
            WHERE role = 'user' AND
                LOWER(msg) LIKE ?""",
           (f'%{lower_text}%',),
           return_type='list')

        input_tokens = lower_text.split()

        # This stores all possible continuations
        all_continuations = []

        for message in all_messages:
            # Find the continuation of the input_text in message
            if message.lower().startswith(lower_text):
                continuation = message[len(lower_text):].strip()
                all_continuations.append(continuation)

        # Tokenize the continuations per character
        continuation_tokens = [cont.split() for cont in all_continuations if cont]
        # continuation_tokens = [cont.split() for cont in all_continuations if cont]

        # Count the frequency of each word at each position
        freq_dist = {}
        for tokens in continuation_tokens:
            for i, token in enumerate(tokens):
                if i not in freq_dist:
                    freq_dist[i] = Counter()
                freq_dist[i][token] += 1

        # Find the cutoff point. You'll need to define the condition for a "dramatic change."
        cutoff = -1
        for i in sorted(freq_dist.keys()):
            # An example condition: If the most common token frequency at position i drops by more than 70% compared to position i-1
            if i > 0 and max(freq_dist[i].values()) < 0.6 * max(freq_dist[i - 1].values()):
                cutoff = i
                break
        if cutoff == -1:  # If no dramatic change is detected.
            # cutoff = max(freq_dist.keys())
            return ''

        # Reconstruct the most likely continuation
        continuation = []

        for i in range(cutoff + 1):
            if freq_dist[i]:
                most_common_token = freq_dist[i].most_common(1)[0][0]
                continuation.append(most_common_token)

        suggested_continuation = ' '.join(continuation)
        return suggested_continuation

    def sizeHint(self):
        doc = QTextDocument()
        doc.setDefaultFont(self.font)
        doc.setPlainText(self.toPlainText())

        # Calculate the height based on the text
        height = doc.size().height() + 10
        return QSize(self.width(), min(height, 150))

    files = []

    # mouse hover event show mic button
    def enterEvent(self, event):
        self.button_bar.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.button_bar.hide()
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
    def __init__(self, parent):
        super().__init__(parent=parent, icon_path=":/resources/icon-send.png", opacity=0.7)
        self.parent = parent
        self.setFixedSize(64, 46)
        self.setProperty("class", "send")
        self.update_icon(is_generating=False)

    def update_icon(self, is_generating):
        icon_iden = 'send' if not is_generating else 'stop'
        pixmap = colorize_pixmap(QPixmap(f":/resources/icon-{icon_iden}.png"))
        self.setIconPixmap(pixmap)


class Main(QMainWindow):
    new_sentence_signal = Signal(str, int, str)
    new_enhanced_sentence_signal = Signal(str)
    finished_signal = Signal()
    error_occurred = Signal(str)
    enhancement_error_occurred = Signal(str)
    title_update_signal = Signal(str)

    mouseEntered = Signal()
    mouseLeft = Signal()

    def __init__(self):
        super().__init__()

        self.main = self  # workaround for bubbling up
        screenrect = QApplication.primaryScreen().availableGeometry()
        self.move(screenrect.right() - self.width(), screenrect.bottom() - self.height())

        # self.check_if_app_already_running()
        telemetry.initialize()

        self.check_db()
        self.patch_db()
        self.check_tos()

        self.system = manager
        self.system.load()
        telemetry.set_uuid(self.get_uuid())
        telemetry.send('user_login')

        self.page_history = []

        # # self.setMinimumSize(600, 100)
        # self.resize_grip = QSizeGrip(self)
        # self.resize_grip.setFixedSize(self.resize_grip.sizeHint())

        self.threadpool = QThreadPool()

        self.oldPosition = None
        self.expanded = False
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
        self.setWindowIcon(QIcon(':/resources/icon.png'))

        self.central = QWidget()
        self.central.setProperty("class", "central")
        self.setCentralWidget(self.central)
        self.layout = QVBoxLayout(self.central)

        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self.pinned_pages = set(['Chat', 'Contexts', 'Agents', 'Settings'])  # todo checkmate
        pin_blocks = self.system.config.dict.get('display.pin_blocks', True)
        pin_tools = self.system.config.dict.get('display.pin_tools', True)
        if pin_blocks:
            self.pinned_pages.add('Blocks')
        if pin_tools:
            self.pinned_pages.add('Tools')

        self.main_menu = MainPages(self)

        self.page_chat = self.main_menu.pages['Chat']
        self.page_contexts = self.main_menu.pages['Contexts']
        self.page_agents = self.main_menu.pages['Agents']
        self.page_settings = self.main_menu.pages['Settings']

        self.layout.addWidget(self.main_menu)

        # Message text and send button
        self.message_text = MessageText(self)
        self.send_button = SendButton(self)

        # Horizontal layout for message text and send button
        self.input_container = QWidget()
        hlayout = CHBoxLayout(self.input_container)
        hlayout.addWidget(self.message_text)
        # hlayout.addWidget(self.button_bar)
        hlayout.addWidget(self.send_button)

        self.layout.addWidget(self.input_container)

        self.send_button.clicked.connect(self.page_chat.on_send_message)
        self.message_text.enterPressed.connect(self.page_chat.on_send_message)

        # self.new_bubble_signal.connect(self.page_chat.insert_bubble, Qt.QueuedConnection)
        self.new_sentence_signal.connect(self.page_chat.message_collection.new_sentence, Qt.QueuedConnection)
        self.new_enhanced_sentence_signal.connect(self.message_text.button_bar.enhance_button.on_new_enhanced_sentence, Qt.QueuedConnection)
        self.finished_signal.connect(self.page_chat.message_collection.on_receive_finished, Qt.QueuedConnection)
        self.error_occurred.connect(self.page_chat.message_collection.on_error_occurred, Qt.QueuedConnection)
        self.enhancement_error_occurred.connect(self.message_text.button_bar.enhance_button.on_enhancement_error, Qt.QueuedConnection)
        self.title_update_signal.connect(self.page_chat.on_title_update, Qt.QueuedConnection)

        app_config = self.system.config.dict
        self.page_settings.load_config(app_config)

        self.show()
        self.main_menu.load()

        is_in_ide = 'ANTHROPIC_API_KEY' in os.environ
        dev_mode_state = True if is_in_ide else None
        self.main_menu.pages['Settings'].pages['System'].toggle_dev_mode(dev_mode_state)

        # self.main_menu.settings_sidebar.btn_new_context.setFocus()
        self.apply_stylesheet()
        self.apply_margin()
        self.activateWindow()

        # # Redirect stdout and stderr
        # sys.stdout = OutputRedirector(self.message_text)
        # sys.stderr = sys.stdout

    def get_uuid(self):
        my_uuid = sql.get_scalar("SELECT value FROM settings WHERE `field` = 'my_uuid'")
        if my_uuid == '':
            my_uuid = str(uuid.uuid4())
            sql.execute("UPDATE settings SET value = ? WHERE `field` = 'my_uuid'", (my_uuid,))
        return my_uuid

    def check_tos(self):
        is_accepted = sql.get_scalar("SELECT value FROM settings WHERE `field` = 'accepted_tos'")
        if is_accepted == '1':
            return

        dialog = TOSDialog()
        if dialog.exec() == QDialog.Accepted:
            sql.execute("UPDATE settings SET value = '1' WHERE `field` = 'accepted_tos'")
            return
        else:
            sys.exit(0)

    def check_db(self):
        # Check if the database is up-to-date
        try:
            upgrade_db = sql.check_database_upgrade()
            if upgrade_db:
                # ask confirmation first
                if QMessageBox.question(None, "Database outdated",
                                        "Do you want to upgrade the database to the newer version?",
                                        QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                    # exit the app
                    sys.exit(0)

                db_version = upgrade_db
                upgrade_script.upgrade(current_version=db_version)

        except Exception as e:
            text = str(e)
            if hasattr(e, 'message'):
                if e.message == 'NO_DB':
                    text = "No database found. Please make sure `data.db` is located in the same directory as this executable."
                elif e.message == 'OUTDATED_APP':
                    text = "The database originates from a newer version of Agent Pilot. Please download the latest version from github."
            display_messagebox(icon=QMessageBox.Critical, title="Error", text=text)
            sys.exit(0)

    def patch_db(self):
        # Delete from models where `api_id` is a non existing `id` in `apis`
        sql.execute("DELETE FROM models WHERE api_id NOT IN (SELECT id FROM apis)")

        sql.execute("UPDATE apis SET provider_plugin = 'litellm' WHERE provider_plugin = '' OR provider_plugin IS NULL")

        # # create table if not exists
        # sql.execute("""
        #     CREATE TABLE IF NOT EXISTS `evals` (
        #         "id"  INTEGER,
        #         "name"    TEXT,
        #         "config"  TEXT DEFAULT '{}',
        #         "folder_id"	INTEGER DEFAULT NULL,
        #         PRIMARY KEY("id" AUTOINCREMENT)
        #     )""")

        # create table if not exists
        sql.execute("""
            CREATE TABLE IF NOT EXISTS `workspaces` (
                "id"  INTEGER,
                "name"    TEXT,
                "config"  TEXT DEFAULT '{}',
                "folder_id"	INTEGER DEFAULT NULL,
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")

        # if logs table has 3 columns
        col_count = sql.get_scalar("SELECT COUNT(*) FROM pragma_table_info('logs');")
        if col_count == 3:
            sql.execute("""
                CREATE TABLE logs_new (
                    "id"  INTEGER,
                    "name"    TEXT,
                    "config"  TEXT DEFAULT '{}',
                    "folder_id"	INTEGER DEFAULT NULL,
                    PRIMARY KEY("id" AUTOINCREMENT)
                )""")
            sql.execute("""
                INSERT INTO logs_new (id, name, config, folder_id)
                SELECT id, log_type, message, NULL
                FROM logs
                """)
            sql.execute("DROP TABLE logs")
            sql.execute("ALTER TABLE logs_new RENAME TO logs")

        sql.execute("""
            CREATE TABLE IF NOT EXISTS pypi_packages (
                "name"	TEXT,
                "folder_id"	INTEGER DEFAULT NULL,
                PRIMARY KEY("name")
            )""")

        # if models table has schema_plugin
        schema_plugin_col_cnt = sql.get_scalar("SELECT COUNT(*) FROM pragma_table_info('models') WHERE `name` = 'schema_plugin'")
        has_schema_plugin_column = (schema_plugin_col_cnt == '1')
        if has_schema_plugin_column:
            # removes `schema_plugin` column
            sql.execute("""
                CREATE TABLE "models_new" (
                    "id"	INTEGER,
                    "api_id"	INTEGER NOT NULL DEFAULT 0,
                    "name"	TEXT NOT NULL DEFAULT '',
                    "kind"	TEXT NOT NULL DEFAULT 'CHAT',
                    "config"	TEXT NOT NULL DEFAULT '{}',
                    "folder_id"	INTEGER DEFAULT NULL, 
                    schema_plugin TEXT DEFAULT '',
                    PRIMARY KEY("id" AUTOINCREMENT)
                )""")
            sql.execute("""
                INSERT INTO models_new (id, api_id, name, kind, config, folder_id)
                SELECT id, api_id, name, kind, config, folder_id
                FROM models
            """)
            sql.execute("DROP TABLE models")
            sql.execute("ALTER TABLE models_new RENAME TO models")

        # sql.execute("""
        #     UPDATE blocks
        #     SET config = json_set(config, '$.data', REPLACE(REPLACE(json_extract(config, '$.data'), '{{', '{'), '}}', '}'))
        #     WHERE COALESCE(json_extract(config, '$.block_type'), 'Text') = 'Text'
        # """)
        # sql.execute("""
        #     UPDATE blocks
        #     SET config = json_set(config, '$.data', REPLACE(REPLACE(json_extract(config, '$.data'), '{', '{{'), '}', '}}'))
        #     WHERE COALESCE(json_extract(config, '$.block_type'), 'Text') = 'Text'
        # """)

        # This is structure of contexts config
        # sql.execute("""
        #     UPDATE contexts_new
        #     SET config = (
        #         SELECT json_object(
        #             '_TYPE', 'workflow',
        #             'members', (
        #                 SELECT json_group_array(
        #                     json_object(
        #                         'id', ordered_cm.id,
        #                         'agent_id', ordered_cm.agent_id,
        #                         'loc_x', ordered_cm.loc_x,
        #                         'loc_y', ordered_cm.loc_y,
        #                         'config', json(ordered_cm.config),
        #                         'del', ordered_cm.del
        #                     )
        #                 )
        #                 FROM (
        #                     SELECT
        #                         1 as id,
        #                         NULL as agent_id,
        #                         -10 as loc_x,
        #                         64 as loc_y,
        #                         '{"_TYPE": "user"}' as config,
        #                         0 as del,
        #                         0 as order_col -- This is to ensure the user member comes first
        #                     UNION ALL
        #                     SELECT
        #                         cm.id,
        #                         cm.agent_id,
        #                         cm.loc_x,
        #                         cm.loc_y,
        #                         cm.agent_config as config,
        #                         cm.del,
        #                         1 as order_col -- This is for actual members to come after the user member
        #                     FROM contexts_members cm
        #                     WHERE cm.context_id = contexts_new.id
        #                 ) as ordered_cm
        #                 ORDER BY ordered_cm.order_col, ordered_cm.id -- Ensures correct order in the output
        #             ),
        #             'inputs', (
        #                 SELECT json_group_array(
        #                     json_object(
        #                         'member_id', cmi.member_id,
        #                         'input_member_id', COALESCE(cmi.input_member_id, 1),
        #                         'type', cmi.type
        #                     )
        #                 )
        #                 FROM contexts_members_inputs cmi
        #                 WHERE cmi.member_id IN (
        #                     SELECT id FROM contexts_members WHERE context_id = contexts_new.id
        #                 )
        #             )
        #         )
        #     )""")

        # Like the blocks, we need to update the contexts config to have the correct double curly braces
        # sql.execute("""
        #     UPDATE contexts
        #     SET config = json_set(config, '$.data', REPLACE(REPLACE(json_extract(config, '$.data'), '{{', '{'), '}}', '}'))

        # if contexts table has 'kind' column
        kind_col_cnt = sql.get_scalar("SELECT COUNT(*) FROM pragma_table_info('contexts') WHERE `name` = 'kind'")
        has_kind_column = (kind_col_cnt == '1')
        if not has_kind_column:
            sql.execute("""
                CREATE TABLE "contexts_new" (
                        "id"	INTEGER,
                        "parent_id"	INTEGER,
                        "branch_msg_id"	INTEGER DEFAULT NULL,
                        "name"	TEXT NOT NULL DEFAULT '',
                        "kind"	TEXT NOT NULL DEFAULT 'CHAT',
                        "active"	INTEGER NOT NULL DEFAULT 1,
                        "folder_id"	INTEGER DEFAULT NULL,
                        "ordr"	INTEGER DEFAULT 0,
                        "config"	TEXT NOT NULL DEFAULT '{}',
                        PRIMARY KEY("id" AUTOINCREMENT)
                    )
            """)
            sql.execute("""
                INSERT INTO contexts_new (id, parent_id, branch_msg_id, name, kind, active, folder_id, ordr, config)
                SELECT id, parent_id, branch_msg_id, name, 'CHAT', active, folder_id, ordr, config
                FROM contexts
            """)
            sql.execute("DROP TABLE contexts")
            sql.execute("ALTER TABLE contexts_new RENAME TO contexts")

    # def check_if_app_already_running(self):
    #     # if not getattr(sys, 'frozen', False):
    #     #     return  # Don't check if we are running in ide
    #
    #     current_pid = os.getpid()  # Get the current process ID
    #
    #     for proc in psutil.process_iter(['pid', 'name']):
    #         try:
    #             proc_info = proc.as_dict(attrs=['pid', 'name'])
    #             if proc_info['pid'] != current_pid and 'AgentPilot' in proc_info['name']:
    #                 raise Exception("Another instance of the application is already running.")
    #         except (psutil.NoSuchProcess, psutil.AccessDenied):
    #             # If the process no longer exists or there's no permission to access it, skip it
    #             continue

    def apply_stylesheet(self):
        QApplication.instance().setStyleSheet(get_stylesheet(self))

        # pixmaps
        for child in self.findChildren(IconButton):
            child.setIconPixmap()
        # trees
        for child in self.findChildren(QTreeWidget):
            child.apply_stylesheet()

        text_color = self.system.config.dict.get('display.text_color', '#c4c4c4')
        self.page_chat.top_bar.title_label.setStyleSheet(f"QLineEdit {{ color: {apply_alpha_to_hex(text_color, 0.90)}; background-color: transparent; }}"
                                           f"QLineEdit:hover {{ color: {text_color}; }}")

    def apply_margin(self):
        margin = self.system.config.dict.get('display.window_margin', 6)
        self.layout.setContentsMargins(margin, margin, margin, margin)

    def sync_send_button_size(self):
        self.send_button.setFixedHeight(self.message_text.height())
        self.message_text.button_bar.setFixedHeight(self.message_text.height())
        self.message_text.button_bar.mic_button.setFixedHeight(int(self.message_text.height() / 2))
        self.message_text.button_bar.enhance_button.setFixedHeight(int(self.message_text.height() / 2))

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
        win_bottom = win_y + win_height >= screen_height - 75
        is_right_corner = win_right and win_bottom
        return is_right_corner

    def collapse(self):
        global PIN_MODE
        if PIN_MODE:
            return
        if not self.expanded:
            return
        self.expanded = False
        # self.content_container.hide()
        self.main_menu.hide()

        self.apply_stylesheet()  # set top right border radius to 0
        if self.is_bottom_corner():
            self.message_text.hide()
            self.send_button.hide()
            self.change_width(50)
            # self.setStyleSheet("border-top-right-radius: 0px; border-bottom-left-radius: 0px;")

        # QApplication.processEvents()
        self.change_height(self.message_text.height() + 16)

    def expand(self):
        if self.expanded:
            return
        self.expanded = True
        self.apply_stylesheet()
        self.change_height(800)
        self.change_width(720)
        self.main_menu.show()
        self.message_text.show()
        self.send_button.show()

    def toggle_always_on_top(self):
        always_on_top = self.system.config.dict.get('system.always_on_top', True)

        current_flags = self.windowFlags()
        new_flags = current_flags

        # Set or unset the always-on-top flag depending on the setting
        if always_on_top:
            new_flags |= Qt.WindowStaysOnTopHint
        else:
            new_flags &= ~Qt.WindowStaysOnTopHint

        # Hide the window before applying new flags
        self.hide()
        self.setWindowFlags(new_flags)

        # Ensuring window borders and transparency
        self.setAttribute(Qt.WA_TranslucentBackground)  # Maintain transparency
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)  # Keep it frameless
        self.show()

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
        self.resize(self.width(), height)
        self.move(self.x(), self.y() - (height - old_height))

    def change_width(self, width):
        old_width = self.width()
        self.resize(width, self.height())
        self.move(self.x() - (width - old_width), self.y())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_resize_grip_position()

    def moveEvent(self, event):
        super().moveEvent(event)
        self.update_resize_grip_position()

    def update_resize_grip_position(self):
        pass
        # x = 0  # Top-left corner
        # y = 0  # Top-left corner
        # self.resize_grip.move(x, y)

    # def sizeHint(self):
    #     return QSize(600, 100)

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


def launch(db_path=None):
    try:
        sql.set_db_filepath(db_path)

        app = QApplication(sys.argv)
        # locale = QLocale.system().name()
        # translator = QTranslator()
        # if translator.load(':/lang/es.qm'):  # + QLocale.system().name()):
        #     app.installTranslator(translator)

        m = Main()  # system=system)
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
