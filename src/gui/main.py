
import json
import os
import sys
import uuid

import nest_asyncio
from PySide6.QtWidgets import *
from PySide6.QtCore import Signal, QSize, QTimer, QEvent, QThreadPool, QPoint, QPropertyAnimation, QEasingCurve, \
    QObject, Slot
from PySide6.QtGui import QPixmap, QIcon, QFont, QTextCursor, QTextDocument, QFontMetrics, QGuiApplication, Qt, \
    QPainter, QColor, QPen, QPainterPath

from src.gui.pages.blocks import Page_Block_Settings
from src.gui.pages.modules import Page_Module_Settings
from src.gui.pages.tools import Page_Tool_Settings
from src.utils.reset import ensure_system_folders
from src.utils.sql_upgrade import upgrade_script
from src.utils import sql, telemetry
from src.system.base import manager

from src.gui.pages.chat import Page_Chat
from src.gui.pages.settings import Page_Settings
from src.gui.pages.agents import Page_Entities
from src.gui.pages.contexts import Page_Contexts
from src.utils.helpers import display_message_box, apply_alpha_to_hex, get_avatar_paths_from_config, path_to_pixmap, \
    convert_to_safe_case, display_message, get_metadata
from src.gui.style import get_stylesheet
from src.gui.config import CVBoxLayout, CHBoxLayout, ConfigPages, get_selected_pages, set_selected_pages
from src.gui.widgets import IconButton, colorize_pixmap, TextEnhancerButton, ToggleIconButton, find_main_widget

os.environ["QT_OPENGL"] = "software"

nest_asyncio.apply()

BOTTOM_CORNER_X = 400
BOTTOM_CORNER_Y = 450

PIN_MODE = True


class TutorialHighlightWidget(QWidget):
    clicked_target = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        # self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)

        self.setStyleSheet("border-top-left-radius: 30px;")
        self.target_pos = QPoint(90, 60)
        self.target_radius = 50
        self.message = ""

        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            if (event.pos() - self.target_pos).manhattanLength() <= self.target_radius:
                self.clicked_target.emit()
                return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        # call parent mousePressEvent
        self.parent.mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # event.ignore()
        super().mouseMoveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Create a path for the entire widget
        full_path = QPainterPath()
        full_path.addRect(self.rect())

        # Create a path for the circular cutout
        circle_path = QPainterPath()
        circle_path.addEllipse(self.target_pos, self.target_radius, self.target_radius)

        # Subtract the circle path from the full path
        dimmed_path = full_path.subtracted(circle_path)

        # Draw dimmed overlay
        painter.setBrush(QColor(0, 0, 0, 128))
        painter.setPen(Qt.NoPen)
        painter.drawPath(dimmed_path)

        # Draw circle border
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(Qt.white, 2))
        painter.drawEllipse(self.target_pos, self.target_radius, self.target_radius)

        # Draw message
        if self.message:
            painter.setPen(Qt.white)
            painter.drawText(self.rect(), Qt.AlignBottom | Qt.AlignHCenter, self.message)

    def set_target(self, pos, radius, message=""):
        self.target_pos = pos
        self.target_radius = radius
        self.message = message
        self.update()


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
        # self.btn_pin = IconButton(parent=self, icon_path=":/resources/icon-pin-on.png", size=20, opacity=0.7)
        self.btn_close = IconButton(parent=self, icon_path=":/resources/close.png", size=20, opacity=0.7)
        self.btn_minimise.clicked.connect(self.window_action)
        # self.btn_pin.clicked.connect(self.toggle_pin)
        self.btn_close.clicked.connect(self.closeApp)

        self.layout = CHBoxLayout(self)
        self.layout.addStretch(1)
        self.layout.addWidget(self.btn_minimise)
        # self.layout.addWidget(self.btn_pin)
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
        )
        self.parent = parent
        self.main = parent
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.title_bar = TitleButtonBar(parent=self)

        # build initial pages
        self.page_selections = None
        # self.locked_above = ['Tasks', 'Settings']
        self.locked_above = ['Settings']
        self.locked_below = ['Modules', 'Tools', 'Blocks', 'Agents', 'Contexts', 'Chat']
        # self.pages = {}
        self.pages['Settings'] = Page_Settings(parent=parent)
        self.pages['Modules'] = Page_Module_Settings(parent=parent)
        self.pages['Tools'] = Page_Tool_Settings(parent=parent)
        self.pages['Blocks'] = Page_Block_Settings(parent=parent)
        self.pages['Agents'] = Page_Entities(parent=parent)
        self.pages['Contexts'] = Page_Contexts(parent=parent)
        self.pages['Chat'] = Page_Chat(parent=parent)

        self.build_custom_pages()

        if self.default_page:
            default_page = self.pages.get(self.default_page)
            page_index = self.content.indexOf(default_page)
            self.content.setCurrentIndex(page_index)
            pass

    def build_custom_pages(self):  # todo dedupe
        # rebuild self.pages efficiently with custom pages inbetween locked pages
        self.page_selections = get_selected_pages(self)

        from src.system.modules import get_page_definitions
        page_definitions = get_page_definitions(with_ids=True)
        new_pages = {}
        for page_name in self.locked_above:
            new_pages[page_name] = self.pages[page_name]
        for key, page_class in page_definitions.items():
            module_id, page_name = key
            try:
                new_pages[page_name] = page_class(parent=self.parent)
                setattr(new_pages[page_name], 'module_id', module_id)
                setattr(new_pages[page_name], 'propagate', False)
                existing_page = self.pages.get(page_name, None)
                if existing_page and getattr(existing_page, 'user_editing', False):
                    setattr(new_pages[page_name], 'user_editing', True)

            except Exception as e:
                display_message(self, f"Error loading page '{page_name}':\n{e}", 'Error', QMessageBox.Warning)

        for page_name in self.locked_below:
            new_pages[page_name] = self.pages[page_name]
        self.pages = new_pages
        self.build_schema()
        pass

    def build_schema(self):
        """OVERRIDES DEFAULT. Build the widgets of all pages from `self.pages`"""
        # remove all widgets from the content stack if not in self.pages
        for i in reversed(range(self.content.count())):
            remove_widget = self.content.widget(i)
            if remove_widget in self.pages.values():
                continue
            self.content.removeWidget(remove_widget)
            remove_widget.deleteLater()

        # remove settings sidebar
        if getattr(self, 'settings_sidebar', None):
            self.layout.removeWidget(self.settings_sidebar)
            self.settings_sidebar.deleteLater()

        for i, (page_name, page) in enumerate(self.pages.items()):
            widget = self.content.widget(i)
            if widget == page:
                continue

            self.content.insertWidget(i, page)
            if hasattr(page, 'build_schema'):
                try:
                    page.build_schema()
                except Exception as e:
                    display_message(self, f'Error loading page "{page_name}": {e}', 'Error', QMessageBox.Warning)

        self.settings_sidebar = self.ConfigSidebarWidget(parent=self)
        self.settings_sidebar.layout.insertWidget(0, self.title_bar)
        self.settings_sidebar.layout.insertStretch(1, 1)  # todo, now user can't use bottom_to_top feature
        self.settings_sidebar.setFixedWidth(70)
        self.settings_sidebar.setContentsMargins(4,0,0,4)

        setattr(self.settings_sidebar, 'new_page_btn', IconButton(
            parent=self.settings_sidebar,
            # icon_path=':/resources/icon-blocks.png',
            hover_icon_path=':/resources/icon-new-large.png',
            size=50,
            # opacity=0.7
        ))
        self.settings_sidebar.new_page_btn.clicked.connect(self.new_page_btn_clicked)
        self.settings_sidebar.layout.insertWidget(2, self.settings_sidebar.new_page_btn)

        layout = CHBoxLayout()
        if not self.right_to_left:
            layout.addWidget(self.settings_sidebar)
            layout.addWidget(self.content)
        else:
            layout.addWidget(self.content)
            layout.addWidget(self.settings_sidebar)

        last_layout = self.layout.takeAt(self.layout.count() - 1)
        if last_layout:
            del last_layout

        self.layout.addLayout(layout)

        if self.page_selections:
            set_selected_pages(self, self.page_selections)
            pass

    def load(self):
        super().load()

        current_page_is_chat = self.content.currentWidget() == self.pages['Chat']
        icon_iden = 'chat' if not current_page_is_chat else 'new-large'
        icon_pixmap = QPixmap(f":/resources/icon-{icon_iden}.png")
        if self.settings_sidebar:
            self.settings_sidebar.page_buttons['Chat'].setIconPixmap(icon_pixmap)

    def new_page_btn_clicked(self):
        dlg_title, dlg_prompt = ('New page name', 'Enter a new name for the new page')
        text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt)
        if not ok:
            return

        # text = text
        safe_text = convert_to_safe_case(text).capitalize()
        module_code = f"""
from src.gui.config import ConfigWidget, ConfigFields, ConfigJoined, ConfigTabs, ConfigPages, ConfigDBTree, CVBoxLayout, CHBoxLayout

class Page_{safe_text}_Settings(ConfigPages):
    def __init__(self, parent):
        super().__init__(parent=parent)
        # self.icon_path = ":/resources/icon-tasks.png"
        self.try_add_breadcrumb_widget(root_title=\"\"\"{text}\"\"\")
        self.pages = {{}}
"""

        module_config = {
            'load_on_startup': True,
            'data': module_code
        }
        module_metadata = get_metadata(module_config)

        pages_module_folder_id = sql.get_scalar("""
            SELECT id
            FROM folders
            WHERE name = 'Pages'
                AND type = 'modules'
        """)
        if not pages_module_folder_id:
            display_message(self, 'Could not find the "Pages" module folder', 'Error', QMessageBox.Critical)
            return

        sql.execute("""
            INSERT INTO modules (name, config, metadata, folder_id)
            VALUES (?, ?, ?, ?)
        """, (text, json.dumps(module_config), json.dumps(module_metadata), pages_module_folder_id))

        from src.system.base import manager
        manager.load('modules')
        main = find_main_widget(self)
        main.main_menu.build_custom_pages()
        main.page_settings.build_schema()  # !! #
        main.main_menu.settings_sidebar.toggle_page_pin(text, True)
        page_btn = main.main_menu.settings_sidebar.page_buttons.get(text, None)
        if page_btn:
            page_btn.click()
            main.main_menu.settings_sidebar.edit_page(text)


class MessageButtonBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.parent = parent
        self.mic_button = self.MicButton(self)
        self.enhance_button = TextEnhancerButton(self, self.parent, gen_block_folder_name='Enhance prompt')
        self.edit_button = self.EditButton(self)
        self.screenshot_button = self.ScreenshotButton(self)

        self.layout = CVBoxLayout(self)
        h_layout = CHBoxLayout()
        h_layout.addWidget(self.mic_button)
        h_layout.addWidget(self.edit_button)
        self.layout.addLayout(h_layout)

        h2_layout = CHBoxLayout()
        h2_layout.addWidget(self.enhance_button)
        h2_layout.addWidget(self.screenshot_button)
        self.layout.addLayout(h2_layout)

        self.hide()

    class EditButton(IconButton):
        def __init__(self, parent):
            super().__init__(parent=parent, icon_path=':/resources/icon-dots.png', size=20, opacity=0.75)
            self.setProperty("class", "send")
            self.clicked.connect(self.on_clicked)

        def on_clicked(self):
            pass

    class ScreenshotButton(IconButton):
        def __init__(self, parent):
            super().__init__(parent=parent, icon_path=':/resources/icon-screenshot.png', size=20, opacity=0.75)
            self.setProperty("class", "send")
            self.clicked.connect(self.on_clicked)

        def on_clicked(self):
            # minimize app, take screenshot, maximize app
            main = find_main_widget(self)

            try:
                import pyautogui
                pyautogui.screenshot()  # check missing lib before minimizing
                main.showMinimized()
                screenshot = pyautogui.screenshot()
                main.showNormal()
                b64 = screenshot.tobytes()
                print(b64)
            except Exception as e:
                display_message(self, f'Error taking screenshot: {e}', 'Error', QMessageBox.Warning)
            finally:
                main.showNormal()

    class MicButton(ToggleIconButton):
        def __init__(self, parent):
            super().__init__(parent=parent, icon_path=':/resources/icon-mic.png', color_when_checked='#6aab73', size=20, opacity=0.75)
            self.setProperty("class", "send")
            self.recording = False


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


class NotificationWidget(QWidget):
    closed = Signal(QObject)

    def __init__(self, parent=None, color=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        if not color:
            color = '#ff6464'
        if color == 'blue':
            color = '#438BB9'
        elif not color.startswith('#'):
            color = '#ff6464'

        self.setStyleSheet(f"""
            background-color: {color};
            border-radius: 10px;
            color: white;
            padding: 10px;
        """)
        self.setMaximumWidth(300)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.content = QWidget(self)
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.label = QLabel()
        self.label.setWordWrap(True)
        content_layout.addWidget(self.label)

        outer_layout.addWidget(self.content)

        self.content.setMinimumHeight(0)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide_animation)

        self.animation = QPropertyAnimation(self.content, b"minimumHeight")
        self.animation.setEasingCurve(QEasingCurve.InOutCubic)
        self.animation.finished.connect(self.on_animation_finished)

    def show_message(self, message, duration=3000):
        self.label.setText(message)
        self.label.adjustSize()
        self.content.adjustSize()
        self.adjustSize()

        QApplication.processEvents()  # todo

        self.content.setMinimumHeight(0)

        target_height = self.content.sizeHint().height()

        self.animation.stop()
        self.animation.setStartValue(0)
        self.animation.setEndValue(target_height)
        self.animation.setDuration(300)
        self.animation.start()

        self.timer.start(duration)

    def hide_animation(self):
        current_height = self.content.minimumHeight()
        self.animation.stop()
        self.animation.setStartValue(current_height)
        self.animation.setEndValue(0)
        self.animation.setDuration(300)
        self.animation.start()

    def on_animation_finished(self):
        if self.content.minimumHeight() == 0:
            self.hide()
            self.closed.emit(self)

    def enterEvent(self, event):
        self.timer.stop()
        event.accept()

    def leaveEvent(self, event):
        self.timer.start(3000)
        event.accept()


class NotificationManager(QWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.main = parent
        self.setFixedWidth(300)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)  # Add this line
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)

        self.layout = CVBoxLayout(self)
        self.layout.setSpacing(4)
        self.layout.setAlignment(Qt.AlignTop)

        self.notifications = []

    def show_notification(self, message, color=None):
        notification = NotificationWidget(self.main, color=color)
        notification.closed.connect(self.remove_notification)
        notif_layout = CHBoxLayout()
        spacer = QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum)
        notif_layout.addItem(spacer)
        notif_layout.addWidget(notification)
        self.layout.addLayout(notif_layout)

        notification.show_message(message)
        self.notifications.append(notification)

        self.show()
        self.adjustSize()
        self.update_position()

    def remove_notification(self, notification):
        if notification in self.notifications:
            self.notifications.remove(notification)
            self.layout.removeWidget(notification)
            notification.deleteLater()
            self.adjustSize()
            self.update_position()
        if len(self.notifications) == 0:
            self.hide()

    def update_position(self):
        self.move(self.main.x() + self.main.width() - self.width() - 4, self.main.y() + 50)



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

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.button_bar.move(self.width() - 40, 0)

    def keyPressEvent(self, event):  # todo refactor
        combo = event.keyCombination()
        key = combo.key()
        mod = combo.keyboardModifiers()
        sh = self.sizeHint()

        suggested_continuation = self.overlay.suggested_text
        if suggested_continuation:
            # if tab is pressed and no modifier is pressed
            if key == Qt.Key.Key_Tab and mod == Qt.KeyboardModifier.NoModifier:
                cursor = self.textCursor()
                cursor.insertText(suggested_continuation)
                self.overlay.set_suggested_text('')
                # self.setFixedSize(self.sizeHint())
                self.resize(sh)
                self.setFixedHeight(sh.height())
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

                    self.resize(sh)
                    self.setFixedHeight(sh.height())
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
            self.resize(sh)
            self.setFixedHeight(sh.height())
            self.parent.sync_send_button_size()
            return  # We handle the event, no need to pass it to the base class

        if key == Qt.Key.Key_Enter or key == Qt.Key.Key_Return:
            if mod == Qt.KeyboardModifier.ShiftModifier:
                event.setModifiers(Qt.KeyboardModifier.NoModifier)

                se = super().keyPressEvent(event)
                # self.setFixedSize(self.sizeHint())
                self.resize(sh)
                self.setFixedHeight(sh.height())
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
        self.resize(sh)
        self.setFixedHeight(sh.height())
        self.parent.sync_send_button_size()

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
        if not self.button_bar.mic_button.isChecked():
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


# def test_anthropic():
#     pass
#     tool_collection = ToolCollection(
#         ComputerTool(),
#         # BashTool(),
#         # EditTool(),
#     )
#     to_params = tool_collection.to_params()
#     pass


class Main(QMainWindow):
    new_sentence_signal = Signal(str, str, str)
    finished_signal = Signal()
    error_occurred = Signal(str)
    title_update_signal = Signal(str)
    # task_completed = Signal(str, str)
    show_notification_signal = Signal(str, str)

    mouseEntered = Signal()
    mouseLeft = Signal()

    def __init__(self):
        super().__init__()

        self._mousePressed = False
        self._mousePos = None
        self._mouseGlobalPos = None
        self._resizing = False
        self._resizeMargins = 10  # Margin in pixels to detect resizing

        self.main = self  # workaround for bubbling up
        # self.check_if_app_already_running()
        telemetry.initialize()

        self.check_db()
        self.patch_db()
        self.check_tos()

        self.threadpool = QThreadPool()
        self.chat_threadpool = QThreadPool()
        self.task_threadpool = QThreadPool()

        self.system = manager
        self.system._main_gui = self
        self.system.load()
        self.system.initialize_custom_managers()
        get_stylesheet()  # init stylesheet

        # telemetry.set_uuid(self.get_uuid())
        # telemetry.send('user_login')

        self.page_history = []

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
        # self.setMaximumSize(720, 800)

        self.leave_timer = QTimer(self)
        self.leave_timer.setSingleShot(True)
        self.leave_timer.timeout.connect(self.collapse)

        self.setWindowTitle('AgentPilot')
        self.setWindowIcon(QIcon(':/resources/icon.png'))

        self.central = QWidget()
        self.central.setProperty("class", "central")
        # self.central.setMouseTracking(True)
        self.setCentralWidget(self.central)
        self.layout = QVBoxLayout(self.central)

        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        # Initialize the notification manager
        self.notification_manager = NotificationManager(self)
        self.notification_manager.show()

        # self.pinned_pages = set()
        # self.load_pinned_pages()

        ensure_system_folders()

        self.main_menu = MainPages(self)

        self.page_chat = self.main_menu.pages['Chat']
        self.page_contexts = self.main_menu.pages['Contexts']
        self.page_agents = self.main_menu.pages['Agents']
        self.page_settings = self.main_menu.pages['Settings']

        self.layout.addWidget(self.main_menu)

        self.side_bubbles = self.SideBubbles(self)
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

        self.new_sentence_signal.connect(self.page_chat.message_collection.new_sentence, Qt.QueuedConnection)
        self.finished_signal.connect(self.page_chat.message_collection.on_receive_finished, Qt.QueuedConnection)
        self.error_occurred.connect(self.page_chat.message_collection.on_error_occurred, Qt.QueuedConnection)
        self.title_update_signal.connect(self.page_chat.on_title_update, Qt.QueuedConnection)
        # self.task_completed.connect(self.on_task_completed, Qt.QueuedConnection)
        self.show_notification_signal.connect(self.notification_manager.show_notification, Qt.QueuedConnection)

        app_config = self.system.config.dict
        self.page_settings.load_config(app_config)

        # is_in_ide = 'AP_DEV_MODE' in os.environ
        # dev_mode_state = True if is_in_ide else None
        # self.main_menu.pages['Settings'].pages['System'].widgets[1].toggle_dev_mode(dev_mode_state)

        self.show()
        self.main_menu.load()

        screenrect = QApplication.primaryScreen().availableGeometry()
        self.move(screenrect.right() - self.width(), screenrect.bottom() - self.height())
        # self.main_menu.settings_sidebar.btn_new_context.setFocus()
        self.apply_stylesheet()
        self.apply_margin()
        self.activateWindow()

        self.expand()

        chat_icon_pixmap = QPixmap(f":/resources/icon-new-large.png")  # todo
        self.main_menu.settings_sidebar.page_buttons['Chat'].setIconPixmap(chat_icon_pixmap)

        self.notification_manager.update_position()

    def pinned_pages(self):  # todo?
        all_pinned_pages = {'Chat', 'Contexts', 'Agents', 'Settings'}
        # pinned_pages = self.system.config.dict.get('display.pinned_pages', [])  # !! #
        pinned_pages = sql.get_scalar(
            "SELECT `value` FROM settings WHERE `field` = 'pinned_pages';",
            load_json=True
        )
        all_pinned_pages.update(pinned_pages)
        # page_modules = manager.modules.get_page_modules()
        # all_pinned_pages.update(page_modules)
        return all_pinned_pages

    def pinnable_pages(self):
        all_pinnable_pages = {'Blocks', 'Tools', 'Modules'}
        page_modules = manager.modules.get_page_modules()
        all_pinnable_pages.update(page_modules)
        return all_pinnable_pages

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
            display_message_box(icon=QMessageBox.Critical, title="Error", text=str(e), buttons=QMessageBox.Ok)
            sys.exit(0)

    def patch_db(self):
        pass

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

    def show_side_bubbles(self):
        self.side_bubbles.show()
        # move to top left of the main window
        self.side_bubbles.move(self.x() - self.side_bubbles.width(), self.y())

    def hide_side_bubbles(self):
        self.side_bubbles.hide()

    class SideBubbles(QWidget):
        def __init__(self, main):
            super().__init__(parent=None)
            self.main = main
            self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
            self.setFixedWidth(50)

            # show 3 circles 50x50 px vertically
            self.layout = CVBoxLayout(self)

            self.load()

        def load(self):
            recent_chats = sql.get_results("""
                SELECT config
                FROM contexts
                WHERE kind = 'CHAT'
                ORDER BY id DESC
                LIMIT 3
            """, return_type='list')

            for config in recent_chats:
                config = json.loads(config)
                member_paths = get_avatar_paths_from_config(config)
                member_pixmap = path_to_pixmap(member_paths, diameter=50)
                label = QLabel()
                label.setPixmap(member_pixmap)
                self.layout.addWidget(label)

    def apply_stylesheet(self):
        # QTimer.singleShot(10, lambda: QApplication.instance().setStyleSheet(get_stylesheet(self)))
        QApplication.instance().setStyleSheet(get_stylesheet())
        # pixmaps
        for child in self.findChildren(IconButton):
            child.setIconPixmap()
        pass
        # trees
        for child in self.findChildren(QTreeWidget):
            child.apply_stylesheet()
        pass
            
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
        self.message_text.button_bar.edit_button.setFixedHeight(int(self.message_text.height() / 2))
        self.message_text.button_bar.screenshot_button.setFixedHeight(int(self.message_text.height() / 2))

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
        self.main_menu.hide()

        self.apply_stylesheet()  # set top right border radius to 0
        if self.is_bottom_corner():
            self.message_text.hide()
            self.send_button.hide()
            self.change_width(50)
            # self.setStyleSheet("border-top-right-radius: 0px; border-bottom-left-radius: 0px;")

        self.change_height(self.message_text.height() + 16)

    def expand(self):
        if self.expanded:
            return
        self.expanded = True
        # self.apply_stylesheet()
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
        if event.button() == Qt.LeftButton:
            self._mousePressed = True
            self._mousePos = event.pos()
            self._mouseGlobalPos = event.globalPos()
            self._resizing = self.isMouseOnEdge(event.pos())
            self.updateCursorShape(event.pos())

    def mouseMoveEvent(self, event):
        if self._mousePressed:
            if self._resizing:
                self.resizeWindow(event.globalPos())
            else:
                self.moveWindow(event.globalPos())

    def mouseReleaseEvent(self, event):
        self._mousePressed = False
        self._resizing = False
        self._mousePos = None
        self._mouseGlobalPos = None
        self.setCursor(Qt.ArrowCursor)

    def isMouseOnEdge(self, pos):
        rect = self.rect()
        return (pos.x() < self._resizeMargins or pos.x() > rect.width() - self._resizeMargins or
                pos.y() < self._resizeMargins or pos.y() > rect.height() - self._resizeMargins)

    def moveWindow(self, globalPos):
        if self._mouseGlobalPos is None:
            return
        diff = globalPos - self._mouseGlobalPos
        self.move(self.pos() + diff)
        self._mouseGlobalPos = globalPos
        # self._mousePressed = False
        self.notification_manager.update_position()

    def resizeWindow(self, globalPos):
        diff = globalPos - self._mouseGlobalPos
        newRect = self.geometry()  # Use geometry() instead of rect() to include the window's position

        if self._mousePos.x() < self._resizeMargins:
            newRect.setLeft(newRect.left() + diff.x())
        elif self._mousePos.x() > self.width() - self._resizeMargins:
            newRect.setRight(newRect.right() + diff.x())

        if self._mousePos.y() < self._resizeMargins:
            newRect.setTop(newRect.top() + diff.y())
        elif self._mousePos.y() > self.height() - self._resizeMargins:
            newRect.setBottom(newRect.bottom() + diff.y())

        self.setGeometry(newRect)
        self._mouseGlobalPos = globalPos

    def updateCursorShape(self, pos):
        rect = self.rect()
        left = pos.x() < self._resizeMargins
        right = pos.x() > rect.width() - self._resizeMargins
        top = pos.y() < self._resizeMargins
        bottom = pos.y() > rect.height() - self._resizeMargins

        if (left and top) or (right and bottom):
            self.setCursor(Qt.SizeFDiagCursor)
        elif (left and bottom) or (right and top):
            self.setCursor(Qt.SizeBDiagCursor)
        elif left or right:
            self.setCursor(Qt.SizeHorCursor)
        elif top or bottom:
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

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
        for container in self.page_chat.message_collection.chat_bubbles:
            container.bubble.updateGeometry()
        self.notification_manager.update_position()
        # self.update_resize_grip_position()

    # def moveEvent(self, event):
    #     super().moveEvent(event)
    #     self.update_resize_grip_position()
    #
    # def update_resize_grip_position(self):
    #     # pass
    #     if hasattr(self, 'size_grips'):
    #         self.size_grips[1].move(self.width() - 20, 0)
    #         self.size_grips[2].move(0, self.height() - 20)
    #         self.size_grips[3].move(self.width() - 20, self.height() - 20)
    #
    #     # x = 0  # Top-left corner
    #     # y = 0  # Top-left corner
    #     # self.resize_grip.move(x, y)

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
        app.setAttribute(Qt.AA_EnableHighDpiScaling)
        app.setStyle("Fusion")  # Fixes macos white line issue
        # locale = QLocale.system().name()
        # translator = QTranslator()
        # if translator.load(':/lang/es.qm'):  # + QLocale.system().name()):
        #     app.installTranslator(translator)

        Main()
        app.exec()
    except Exception as e:
        if 'AP_DEV_MODE' in os.environ:
            # When debugging in IDE, re-raise
            raise e
        display_message_box(
            icon=QMessageBox.Critical,
            title='Error',
            text=str(e)
        )
