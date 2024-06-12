import json
import os
import platform
import re
import sys
from collections import Counter, defaultdict

import psutil
import requests
from PySide6.QtWidgets import *
from PySide6.QtCore import Signal, QSize, QTimer, QPoint
from PySide6.QtGui import QPixmap, QIcon, QFont, QTextCursor, QTextDocument, QFontMetrics, QGuiApplication, Qt, \
    QPainter, QColor
from openai import OpenAI
from openai.types.beta.assistant_stream_event import ThreadMessageDelta
from tendo import singleton

from src.plugins.openinterpreter.src import OpenInterpreter
from src.plugins.realtimestt.modules.speech_plugin import RealtimeTTS_Speech
from src.utils.sql_upgrade import upgrade_script
from src.utils import sql
from src.system.base import SystemManager

import logging

from src.gui.pages.chat import Page_Chat
from src.gui.pages.settings import Page_Settings
from src.gui.pages.agents import Page_Entities
from src.gui.pages.contexts import Page_Contexts
from src.utils.helpers import display_messagebox, apply_alpha_to_hex
from src.gui.style import get_stylesheet
from src.gui.config import CVBoxLayout, CHBoxLayout
from src.gui.widgets import IconButton, colorize_pixmap

logging.basicConfig(level=logging.DEBUG)

os.environ["QT_OPENGL"] = "software"


BOTTOM_CORNER_X = 400
BOTTOM_CORNER_Y = 450

PIN_MODE = True


# def test_tel():
#     telemetry_data = {
#         "event": "feature_used",
#         "feature_name": "example_feature",
#         "timestamp": "2023-04-01T12:00:00Z",
#         # ...other relevant data
#     }
#     try:
#         response = requests.post('https://yourdomain.com/telemetry_endpoint', json=telemetry_data)
#         if response.status_code == 200:
#             print("Telemetry data sent successfully")
#         else:
#             print("Failed to send telemetry data")
#     except requests.exceptions.RequestException as e:
#         print("An error occurred while sending telemetry data:", e)
#
#     # Example usage



# def test_oai():
#     client = OpenAI()
#
#     # my_assistant = client.beta.assistants.create(
#     #     instructions="You are a personal math tutor. When asked a question, write and run Python code to answer the question.",
#     #     name="Math Tutor",
#     #     tools=[{"type": "code_interpreter"}],
#     #     model="gpt-4-turbo",
#     # )
#     # print(my_assistant)
#     ass_id = 'asst_RXWHCBsBeP5pTNNo6sb94Y5z'
#
#     run = client.beta.threads.create_and_run(
#         assistant_id=ass_id,
#         stream=True,
#         thread={
#             "messages": [
#                 {
#                     "role": "user",
#                     "content": "Whats the capital of france"
#                 },
#                 {
#                     "role": "assistant",
#                     "content": "Paris"
#                 },
#                 {
#                     "role": "user",
#                     "content": "Germany?"
#                 },
#                 {
#                     "role": "assistant",
#                     "content": "Berlin"
#                 },
#                 {
#                     "role": "user",
#                     "content": "Australia?"
#                 },
#             ]
#         }
#     )
#
#     for event in run:
#         if not isinstance(event, ThreadMessageDelta):
#             continue
#         pass
#         # append print
#         print(event.data.delta.content[0].text.value, end='')


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

        self.layout = CHBoxLayout(self)
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

        self.layout = CVBoxLayout(self)
        self.layout.setSpacing(5)

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
        super().__init__(parent=None)
        self.parent = parent
        # self.setCursor(QCursor(Qt.PointingHandCursor))

        self.mic_button = MicButton(self)

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
        print(f"Suggested continuation: '{continuation}'")

    def auto_complete(self):
        conf = self.parent.system.config.dict
        if not conf.get('system.auto_completion', True):
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

        # # Step 1: Tokenize and analyze frequency of word sequences.
        # # Create a dictionary to store word sequences starting with query_fragment.
        # word_sequences = defaultdict(Counter)
        #
        # for message in all_messages:
        #     words = re.findall(r'\b\w+\b',
        #                        message.lower())  # Extract words assuming they're separated by non-word characters.
        #     for i, word in enumerate(words):
        #         if word == lower_text:
        #             # If the fragment matches, start counting the sequences that follow it.
        #             sequence = tuple(
        #                 words[i:i + 3])  # Change the range as needed for the length of sequences you want to track
        #             next_word = words[i + 1] if i + 1 < len(words) else None
        #             if next_word:
        #                 word_sequences[sequence][next_word] += 1
        #
        # # Step 2: No explicit tree is required, the defaultdict(Counter) is our implicit representation.
        #
        # # Step 3: Traverse the "tree" to find the most common continuation.
        # # We start with the current fragment
        # current_sequence = tuple(lower_text.split())  # Split in case the fragment has multiple words
        # continuation = []
        #
        # while current_sequence in word_sequences:
        #     # Find the most common next word after the current sequence
        #     most_common_next_word, _ = word_sequences[current_sequence].most_common(1)[0]
        #
        #     # Here we could check for the significant drop in frequency.
        #     # If there's a dramatic change, we break out of the loop.
        #
        #     # Add the word to the continuation
        #     continuation.append(most_common_next_word)
        #
        #     # Extend the sequence
        #     current_sequence = (*current_sequence[1:], most_common_next_word)
        #
        # # Join the continuation words to form the suggested text
        # suggested_continuation = ' '.join(continuation)
        #
        # # Final check - remove the trailing incomplete word
        # suggested_continuation = suggested_continuation.rsplit(' ', 1)[0]

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
        # print(f"Suggested continuation: {suggested_continuation}")

        # # show messagebox with all messages count
        # display_messagebox(
        #     icon=QMessageBox.Information,
        #     title='Auto-complete',
        #     text=f'Found {len(all_messages)} messages matching the text.'
        # )

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

# # Function to process messages and find continuations
# def get_most_common_continuation(input_text, all_messages):
#     # Tokenize the input text


class SendButton(IconButton):
    def __init__(self, parent):  # msgbox,
        super().__init__(parent=parent, icon_path=":/resources/icon-send.png", opacity=0.7)
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


# class OutputRedirector:
#     def __init__(self, text_widget):
#         self.text_widget = text_widget
#
#     def write(self, string):
#         # Append text to the QTextEdit widget
#         self.text_widget.append(string)
#
#     def flush(self):
#         # Required for file-like interface
#         pass


class Main(QMainWindow):
    new_sentence_signal = Signal(str, int, str)
    finished_signal = Signal()
    error_occurred = Signal(str)
    title_update_signal = Signal(str)

    mouseEntered = Signal()
    mouseLeft = Signal()

#     def test(self):
#
#         param_dict = {
#             'offline': False,
#             'safe_mode': False,
#             'disable_telemetry': True,
#             'force_task_completion': False,
#             'os': True,
#         }
#         messages = [
#             {'content': 'wh', 'role': 'user', 'type': 'message'},
#             {'content': 'Hi jb! It seems like your message got cut off. How can I assist you today?', 'role': 'assistant', 'type': 'message'},
#             {'content': 'open kazam', 'role': 'user', 'type': 'message'},
#             {'content': 'Let\'s start by trying to open the application "Kazam" on your Linux system by executing a shell command.\n\n**Plan:**\n1. Tr...kazam` command from the command line.\n2. Check the output for any errors or confirmations. \n\nLet\'s execute the first step.', 'role': 'assistant', 'type': 'message'},
#             {'content': 'kazam', 'format': 'shell', 'role': 'assistant', 'type': 'code'},
#             {'role': 'computer', 'type': 'console', 'format': 'output', 'content': '\nWARNING Kazam - Failed to correctly detect operating system.\n\n** (kazam:5209): WARNING **: 15:24:14.488: Binding \'<Super><Ctrl>R\' failed!\n/usr/lib/python3/dist-packages/kazam/app.py:145: Warning: value "((GtkIconSize) 32)" of type \'GtkIconSize\' is invalid or out of range for property \'icon-size\' of type \'GtkIconSize\'\n  self.builder.add_from_file(os.path.join(prefs.datadir, "ui", "kazam.ui"))\n\n(kazam:5209): Gtk-WARNING **: 15:24:14.513: Can\'t set a parent on widget which has a parent\n\n(kazam:5209): Gtk-WARNING **: 15:24:14.518: Can\'t set a parent on widget which has a parent\n'}
#         ]
#         agent_object = OpenInterpreter(**param_dict)
#         for chunk in agent_object.chat(message=messages, display=False, stream=True):
#             pass
# # # 5 = {dict 4}
#
# #         agent_object.chat()
#         pass

    def __init__(self):
        super().__init__()
        # # self.test()
        # # return
        # tst = RealtimeTTS_Speech()
        # tst.transcribe()
        #
        # return

        screenrect = QApplication.primaryScreen().availableGeometry()
        self.move(screenrect.right() - self.width(), screenrect.bottom() - self.height())

        self.check_if_app_already_running()
        self.check_db()

        self.page_history = []

        self.system = SystemManager()

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
        self._layout = QVBoxLayout(self.central)
        self._layout.setSpacing(6)
        self._layout.setContentsMargins(8, 8, 8, 8)

        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self.sidebar = SideBar(self)

        self.content = QStackedWidget(self)
        self.page_chat = Page_Chat(self)
        self.page_settings = Page_Settings(self)
        self.page_agents = Page_Entities(self)
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

        self.send_button.clicked.connect(self.page_chat.on_send_message)
        self.message_text.enterPressed.connect(self.page_chat.on_send_message)

        # self.new_bubble_signal.connect(self.page_chat.insert_bubble, Qt.QueuedConnection)
        self.new_sentence_signal.connect(self.page_chat.new_sentence, Qt.QueuedConnection)
        self.finished_signal.connect(self.page_chat.on_receive_finished, Qt.QueuedConnection)
        self.error_occurred.connect(self.page_chat.on_error_occurred, Qt.QueuedConnection)
        self.title_update_signal.connect(self.page_chat.on_title_update, Qt.QueuedConnection)

        app_config = self.system.config.dict
        self.page_settings.load_config(app_config)
        # self.page_settings.load()

        self.show()
        self.page_chat.load()
        self.page_settings.pages['System'].toggle_dev_mode()

        self.sidebar.btn_new_context.setFocus()
        self.apply_stylesheet()
        self.activateWindow()

        # # Redirect stdout and stderr
        # sys.stdout = OutputRedirector(self.message_text)
        # sys.stderr = sys.stdout

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

                db_version = upgrade_db
                upgrade_script.upgrade(current_version=db_version)

        except Exception as e:
            text = str(e)
            if hasattr(e, 'message'):
                if e.message == 'NO_DB':
                    text = "No database found. Please make sure `data.db` is located in the same directory as this executable."
                elif e.message == 'OUTDATED_APP':
                    text = "The database originates from a newer version of Agent Pilot. Please download the latest version from github."
                elif e.message == 'OUTDATED_DB':
                    text = "The database is outdated. Please download the latest version from github."
            display_messagebox(icon=QMessageBox.Critical, title="Error", text=text)
            sys.exit(0)

    def check_if_app_already_running(self):
        if not getattr(sys, 'frozen', False):
            return  # Don't check if we are running in ide

        for proc in psutil.process_iter():
            if 'AgentPilot' in proc.name():
                raise Exception("Another instance of the application is already running.")

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
        self.content_container.hide()

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
        self.apply_stylesheet()  # reset borders
        self.change_height(750)
        self.change_width(700)
        self.content_container.show()
        self.message_text.show()
        self.send_button.show()
        # self.setStyleSheet("border-radius: 14px; border-top-left-radius: 30px;")

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

    def load_page(self, index):  # , is_undo=False):  # todo clean
        # if not is_undo:
        current_page = self.content.currentWidget()
        current_index = self.content.indexOf(current_page)
        self.page_history.append(current_index)

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
