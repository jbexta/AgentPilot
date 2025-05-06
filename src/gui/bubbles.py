import asyncio
import json
import os
import platform
from typing import Optional, List, Dict, Tuple, Any

from urllib.parse import quote

from PySide6 import QtWidgets
from PySide6.QtWidgets import *
from PySide6.QtCore import QSize, QTimer, QRect, QUrl, QEvent, Slot, QRunnable, QPropertyAnimation, \
    QEasingCurve
from PySide6.QtGui import QPixmap, QIcon, QTextCursor, QTextOption, Qt, QDesktopServices, QTextDocument, QImage

from src.members.user import User
from src.plugins.openinterpreter.src import interpreter

from src.utils.helpers import path_to_pixmap, display_message_box, get_avatar_paths_from_config, \
    get_member_name_from_config, apply_alpha_to_hex, split_lang_and_code, try_parse_json, display_message, \
    message_button, message_extension
from src.gui.widgets import colorize_pixmap, IconButton, find_main_widget, clear_layout, find_workflow_widget
from src.utils import sql
from src.system.base import manager

import mistune

from src.gui.config import CHBoxLayout, CVBoxLayout, ConfigFields
from src.utils.media import play_file
from src.utils.messages import Message


class MessageCollection(QWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.parent = parent
        self.main = find_main_widget(self)
        self.layout = CVBoxLayout(self)
        self.setMinimumHeight(100)

        # self.workflow = workflow  # try to avoid passing workflow
        self.chat_bubbles: List[MessageContainer] = []
        self.last_member_bubbles: Dict[Tuple[str, str], MessageContainer] = {}

        self.temp_text_size = None
        self.show_hidden_messages = False

        self.chat_widget = QWidget(self)
        self.chat_scroll_layout = CVBoxLayout(self.chat_widget)
        bubble_spacing = manager.config.dict.get('display.bubble_spacing', 5)
        self.chat_scroll_layout.setSpacing(bubble_spacing)
        self.chat_scroll_layout.addStretch(1)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidget(self.chat_widget)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.verticalScrollBar().rangeChanged.connect(self.maybe_scroll_to_end)
        self.coupled_scroll = True
        # self.max_scroll_pos = 0
        self.layout.addWidget(self.scroll_area)
        # self.installEventFilterRecursively(self)
        self.scroll_animation = QPropertyAnimation(self.scroll_area.verticalScrollBar(), b"value")

        self.waiting_for_bar = self.WaitingForBar(self)
        self.layout.addWidget(self.waiting_for_bar)
        self.scroll_to_end()

    def maybe_scroll_to_end(self):
        scroll_bar = self.scroll_area.verticalScrollBar()
        val = scroll_bar.value()
        is_at_bottom = scroll_bar.value() >= scroll_bar.maximum() - 50
        if is_at_bottom:
            QTimer.singleShot(50, lambda: self.scroll_to_end())

    def scroll_to_end(self):
        scroll_bar = self.scroll_area.verticalScrollBar()

        if self.scroll_animation.state() == QPropertyAnimation.Running:
            self.scroll_animation.stop()

        self.scroll_animation.setDuration(100)
        self.scroll_animation.setStartValue(scroll_bar.value())
        self.scroll_animation.setEndValue(scroll_bar.maximum())
        self.scroll_animation.setEasingCurve(QEasingCurve.Linear)
        # the different easing curves can be found here: https://doc.qt.io/qt-5/qeasingcurve.html
        self.scroll_animation.start()

    class WaitingForBar(QWidget):
        def __init__(self, parent: QWidget):
            super().__init__(parent)
            self.parent: MessageCollection = parent
            self.layout = CHBoxLayout(self)
            self.layout.setContentsMargins(0, 5, 0, 0)
            self.member_id: Optional[str] = None
            self.member_name_label = None

        def load(self):
            next_member = self.parent.workflow.next_expected_member()
            if not next_member:
                self.hide()
                return

            member_config = next_member.config if next_member else {}

            member_type = member_config.get('_TYPE', 'agent')
            member_name = get_member_name_from_config(member_config)
            if member_type == 'user':
                member_name = 'you'

            clear_layout(self.layout)

            self.member_id = next_member.member_id
            self.member_name_label = QLabel(text=f'Waiting for {member_name}')
            self.member_name_label.setProperty("class", "bubble-name-label")
            self.layout.addWidget(self.member_name_label)

            if member_type != 'user':
                self.play_button = IconButton(
                    parent=self,
                    icon_path=':/resources/icon-run-solid.png',
                    tooltip=f'Resume with {member_name}',
                    size=18,)
                self.play_button.clicked.connect(self.on_play_click)
                self.layout.addWidget(self.play_button)

            self.layout.addStretch(1)

        def on_play_click(self):
            self.parent.run_workflow(from_member_id=self.member_id)

    @property
    def workflow(self):
        return getattr(self.parent, 'workflow', None)

    def load(self):
        self.clear_bubbles()
        self.refresh()
        self.refresh_waiting_bar()

    def refresh(self, block_autorun=False):  # todo block_autorun temp
        with self.workflow.message_history.thread_lock:
            # get scroll position
            scroll_bar = self.scroll_area.verticalScrollBar()
            scroll_pos = scroll_bar.value()

            # # iterate chat_bubbles backwards and find last msg_id that != -1
            last_container = None
            last_container_index = 0
            for i in range(len(self.chat_bubbles) - 1, -1, -1):
                if self.chat_bubbles[i].bubble.msg_id != -1:
                    last_container = self.chat_bubbles[i]
                    last_container_index = i
                    break

            last_bubble_msg_id = last_container.bubble.msg_id if last_container else 0

            proc_cnt = 0
            for msg in self.workflow.message_history.messages:
                if msg.id <= last_bubble_msg_id:
                    continue
                # if msg.member_id.count('.') > 0:
                #     continue
                # get next chat bubble after last_container, or None
                proc_cnt += 1
                if last_container_index + 1 + proc_cnt < len(self.chat_bubbles):
                    self.chat_bubbles[last_container_index + 1 + proc_cnt].load_message(msg)
                else:
                    self.insert_bubble(msg)

            # iterate chat_bubbles backwards and remove any that have id = -1
            for i in range(len(self.chat_bubbles) - 1, -1, -1):
                if self.chat_bubbles[i].bubble.msg_id == -1:
                    bubble_container = self.chat_bubbles.pop(i)
                    self.chat_scroll_layout.removeWidget(bubble_container)
                    bubble_container.hide()  # deleteLater()

            # if last bubble is code then start timer
            if len(self.chat_bubbles) > 0 and not block_autorun:
                last_container = self.chat_bubbles[-1]
                if hasattr(last_container, 'btn_countdown'):
                    autorun_secs = last_container.bubble.autorun_secs
                    last_container.btn_countdown.start_timer(secs=autorun_secs)

            # # Update layout
            self.chat_scroll_layout.update()
            self.updateGeometry()
            scroll_bar.setValue(scroll_pos)

            self.waiting_for_bar.load()
            if self.parent.__class__.__name__ == 'Page_Chat':
                self.parent.top_bar.load()

    def insert_bubble(self, message=None):
        show_bubble = self.parent.main.system.roles.get_role_config(message.role).get('show_bubble', True)
        if not show_bubble:
            return

        msg_container = MessageContainer(self, message=message)
        bubble = msg_container.bubble
        index = len(self.chat_bubbles)
        self.chat_bubbles.insert(index, msg_container)
        self.chat_scroll_layout.insertWidget(index, msg_container)
        self.last_member_bubbles[(bubble.role, bubble.member_id)] = self.chat_bubbles[-1]

    def clear_bubbles(self):
        with self.workflow.message_history.thread_lock:
            while len(self.chat_bubbles) > 0:
                bubble_container = self.chat_bubbles.pop()
                self.chat_scroll_layout.removeWidget(bubble_container)
                bubble_container.hide()  # can't use deleteLater() todo

    def delete_messages_since(self, msg_id):
        with self.workflow.message_history.thread_lock:
            while self.chat_bubbles:
                bubble_cont = self.chat_bubbles.pop()
                bubble_msg_id = bubble_cont.bubble.msg_id
                self.chat_scroll_layout.removeWidget(bubble_cont)
                bubble_cont.hide()  # .deleteLater()
                if bubble_msg_id == msg_id:
                    break

            index = next((i for i, msg in enumerate(self.workflow.message_history.messages) if msg.id == msg_id),
                         -1)

            if index <= len(self.workflow.message_history.messages) - 1:
                self.workflow.message_history.messages[:] = self.workflow.message_history.messages[:index]

    # on send_msg, if last msg alt_turn is same as current, then it's same run
    def send_message(
        self,
        message: str,
        role: str = 'user',
        as_member_id: str = None,  # '1',
        feed_back=False,
        clear_input=False,
        run_workflow=True
    ):  # todo default as_mem_id
        # check if threadpool is active
        if self.main.chat_threadpool.activeThreadCount() > 0:
            return

        if as_member_id is None:  # todo
            members = self.workflow.members
            workflow_first_member = next(iter(sorted(members.values(), key=lambda x: x['loc_x'])), None)

            if workflow_first_member:
                first_member_is_user = isinstance(workflow_first_member, User)
                if first_member_is_user:  # todo de-dupe
                    as_member_id = workflow_first_member.member_id

        last_msg = self.workflow.message_history.messages[-1] if self.workflow.message_history.messages else None
        new_msg = self.workflow.save_message(role, message, member_id=as_member_id)
        if not new_msg:
            return

        if last_msg:
            if last_msg.alt_turn != new_msg.alt_turn:
                self.last_member_bubbles.clear()

        if clear_input:
            self.main.message_text.clear()
            self.main.message_text.setFixedHeight(51)
            self.main.send_button.setFixedHeight(51)

        self.workflow.message_history.load_branches()
        self.refresh(block_autorun=True)

        if role == 'result':
            parsed, res_dict = try_parse_json(message)
            if not parsed or res_dict.get('status') == 'error':
                run_workflow = False

        scroll_bar = self.scroll_area.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())

        self.refresh_waiting_bar()  # set_visibility=False)
        self.parent.workflow_settings.refresh_member_highlights()
        # self.scroll_to_end()
        QTimer.singleShot(5, lambda: self.scroll_to_end())

        if run_workflow:
            self.run_workflow(from_member_id=as_member_id, feed_back=feed_back)  # as_member_id)

    def run_workflow(self, from_member_id=None, feed_back=False):
        self.main.send_button.update_icon(is_generating=True)

        runnable = self.RespondingRunnable(self, from_member_id, feed_back)
        self.main.chat_threadpool.start(runnable)

        if self.parent.__class__.__name__ == 'Page_Chat':
            self.parent.try_generate_title()

    class RespondingRunnable(QRunnable):
        def __init__(self, parent, from_member_id=None, feed_back=False):
            super().__init__()
            self.parent = parent
            self.main = parent.main
            self.from_member_id = from_member_id
            self.feed_back = feed_back  # todo clean

        def run(self):
            try:
                asyncio.run(self.parent.workflow.behaviour.start(self.from_member_id, feed_back=self.feed_back))
                self.main.finished_signal.emit()
            except Exception as e:
                if 'AP_DEV_MODE' in os.environ:
                    raise e  # re-raise the exception for debugging
                self.main.error_occurred.emit(str(e))

    @Slot(str, str, str)
    def new_sentence(self, role, member_id, sentence):
        with self.workflow.message_history.thread_lock:
            if (role, member_id) not in self.last_member_bubbles:
                msg = Message(msg_id=-1, role=role, content=sentence, member_id=member_id)
                self.insert_bubble(msg)
                self.maybe_scroll_to_end()
            else:
                last_member_bubble = self.last_member_bubbles[(role, member_id)]
                last_member_bubble.bubble.append_text(sentence)

    @Slot(str)
    def on_error_occurred(self, error):
        display_message(self,
            message=error,
            icon=QMessageBox.Critical,
        )
        self.end_turn()

    @Slot()
    def on_receive_finished(self):
        self.refresh()
        self.end_turn()

    def end_turn(self):
        with self.workflow.message_history.thread_lock:
            self.last_member_bubbles.clear()
        self.workflow.responding = False
        self.main.send_button.update_icon(is_generating=False)

        self.refresh_waiting_bar(set_visibility=True)
        self.parent.workflow_settings.refresh_member_highlights()

    def refresh_waiting_bar(self, set_visibility=None):
        """Optionally use set_visibility to show or hide, while respecting the system config"""
        workflow_is_multi_member = self.workflow.count_members() > 1
        show_waiting_bar_when = self.main.system.config.dict.get('display.show_waiting_bar', 'In Group')
        show_waiting_bar = ((show_waiting_bar_when == 'In Group' and workflow_is_multi_member)
                            or show_waiting_bar_when == 'Always')
        if show_waiting_bar and set_visibility is not None:
            show_waiting_bar = set_visibility
        self.waiting_for_bar.setVisible(show_waiting_bar)

    def installEventFilterRecursively(self, widget):
        widget.installEventFilter(self)
        for child in widget.children():
            if isinstance(child, QWidget):
                self.installEventFilterRecursively(child)

    def eventFilter(self, watched, event):
        try:
            if event.type() == QEvent.Wheel:
                if event.modifiers() & Qt.ControlModifier:
                    # delta = event.angleDelta().y()
                    #
                    # if delta > 0:
                    #     self.temp_zoom_in()
                    # else:
                    #     self.temp_zoom_out()

                    return True  # Stop further propagation of the wheel event

            if event.type() == QEvent.KeyRelease:
                if event.key() == Qt.Key_Control:
                    # self.update_text_size()

                    return True  # Stop further propagation of the wheel event
        except Exception as e:
            print(e)

        return super().eventFilter(watched, event)


class MessageContainer(QWidget):
    """Container widget for the avatar, bubble and buttons"""

    def __init__(self, parent, message):
        super().__init__(parent=parent)
        self.parent = parent
        self.log_windows = []
        self.setProperty("class", "message-container")
        self.layout = CHBoxLayout(self)  # Avatar / bubble_v_layout / button_v_layout

        self.member_id: str = None
        self.member_config: Dict[str, Any] = {}

        self.bubble: MessageBubble = None
        self.branch_msg_id: int = None
        self.message: Message = None

        self.load_message(message)

    def load_message(self, message):
        clear_layout(self.layout)

        workflow = self.parent.workflow
        self.member_id = message.member_id
        member = workflow.members.get(self.member_id, None)
        self.member_config = getattr(member, 'config') if member else {}
        self.message = message

        # todo temp link bubble modules
        if message.role == 'user':
            bubble_class = UserBubble
        elif message.role == 'assistant':
            bubble_class = AssistantBubble
        elif message.role == 'code':
            bubble_class = CodeBubble
        elif message.role == 'tool':
            bubble_class = ToolBubble
        elif message.role == 'result':
            bubble_class = ResultBubble
        elif message.role == 'image':
            bubble_class = ImageBubble
        elif message.role == 'audio':
            bubble_class = AudioBubble
        else:
            bubble_class = MessageBubble
        self.bubble = bubble_class(parent=self, message=message)

        config = self.parent.main.system.config.dict

        context_is_multi_member = workflow.count_members() > 1
        show_avatar_when = config.get('display.show_bubble_avatar', 'In Group')
        show_name_when = config.get('display.show_bubble_name', 'In Group')
        show_avatar = (show_avatar_when == 'In Group' and context_is_multi_member) or show_avatar_when == 'Always'
        show_name = (show_name_when == 'In Group' and context_is_multi_member) or show_name_when == 'Always'

        if show_avatar:
            agent_avatar_path = get_avatar_paths_from_config(member.config if member else {})
            diameter = workflow.main.system.roles.to_dict().get(message.role, {}).get(
                'display.bubble_image_size', 20
            )
            diameter = int(diameter) if diameter else 0
            circular_pixmap = path_to_pixmap(agent_avatar_path, diameter=diameter)
            if not self.member_config:
                circular_pixmap = colorize_pixmap(circular_pixmap)

            self.profile_pic_label = QLabel(self)
            self.profile_pic_label.setPixmap(circular_pixmap)
            self.profile_pic_label.setFixedSize(30, 30)
            self.profile_pic_label.mousePressEvent = self.view_log

            image_container = QWidget(self)
            image_container_layout = CVBoxLayout(image_container)
            image_container_layout.setContentsMargins(0, 0 if show_name else 4, 0, 0)
            image_container_layout.addWidget(self.profile_pic_label)
            image_container_layout.addStretch(1)

            self.layout.addSpacing(6)
            self.layout.addWidget(image_container)

        bubble_v_layout = CVBoxLayout()  # Name, bubble
        bubble_v_layout.setSpacing(4)

        bubble_h_layout = CHBoxLayout()

        if show_name:
            bubble_v_layout.setContentsMargins(0, 5, 0, 0)
            member_name = get_member_name_from_config(self.member_config)

            self.member_name_label = QLabel(member_name)
            self.member_name_label.setProperty("class", "bubble-name-label")
            bubble_v_layout.addWidget(self.member_name_label)

        bubble_h_layout.addWidget(self.bubble)
        bubble_v_layout.addLayout(bubble_h_layout)

        self.branch_msg_id = message.id

        if getattr(self.bubble, 'has_branches', False):
            branch_layout = CHBoxLayout()
            branch_layout.setSpacing(1)
            self.branch_msg_id = next(iter(self.bubble.branch_entry.keys()))
            self.child_branches = self.bubble.branch_entry[self.branch_msg_id]
            branch_count = len(self.child_branches)
            percent_codes = [int((i + 1) * 100 / (branch_count + 1)) for i in reversed(range(branch_count))]

            for _ in self.child_branches:
                if not percent_codes:
                    break

                bg_bubble = QWidget()
                bg_bubble.setProperty("class", "bubble-bg")
                user_config = self.parent.main.system.roles.get_role_config('user')
                user_bubble_bg_color = user_config.get('bubble_bg_color')
                user_bubble_bg_color = apply_alpha_to_hex(user_bubble_bg_color, percent_codes.pop(0)/100)

                bg_bubble.setStyleSheet(f"background-color: {user_bubble_bg_color}; border-top-left-radius: 2px; "
                                        "border-bottom-left-radius: 2px; border-top-right-radius: 6px; "
                                        "border-bottom-right-radius: 6px;")
                bg_bubble.setFixedWidth(8)
                branch_layout.addWidget(bg_bubble)

            bubble_h_layout.addLayout(branch_layout)

        bubble_h_layout.addStretch(1)

        button_v_layout = CVBoxLayout()
        button_v_layout.setContentsMargins(0, 0, 0, 2)
        button_v_layout.addStretch()

        # get all class definitions in bubble_class decorated with @message_bubble
        bubble_buttons = [
            getattr(bubble_class, attr) for attr in dir(bubble_class)
            if getattr(getattr(bubble_class, attr), '_ap_message_button', None) is not None
        ]
        bubble_buttons = {
            getattr(bubble_button, '_ap_message_button'): bubble_button
            for bubble_button in bubble_buttons
        }

        # get all class definitions in bubble_class decorated with @message_bubble
        bubble_extensions = [
            getattr(bubble_class, attr) for attr in dir(bubble_class)
            if getattr(getattr(bubble_class, attr), '_ap_message_extension', None) is not None
        ]
        bubble_extensions = {
            getattr(bubble_extension, '_ap_message_extension'): bubble_extension
            for bubble_extension in bubble_extensions
        }

        for button_name, bubble_button_cls in bubble_buttons.items():
            bubble_button = bubble_button_cls(self)
            setattr(self, button_name, bubble_button)
            is_autorun = self.bubble.autorun_button == button_name
            if is_autorun:
                btn_countdown = self.CountdownButton(self, target_button=bubble_button)
                setattr(self, 'btn_countdown', btn_countdown)
                countdown_h_layout = CHBoxLayout()
                countdown_h_layout.addWidget(btn_countdown)
                countdown_h_layout.addWidget(bubble_button)
                button_v_layout.addLayout(countdown_h_layout)
            else:
                button_v_layout.addWidget(bubble_button)

        for extension_name, bubble_extension_cls in bubble_extensions.items():
            bubble_extension = bubble_extension_cls(self)
            setattr(self, extension_name, bubble_extension)
            bubble_v_layout.addWidget(bubble_extension)

        self.layout.addLayout(bubble_v_layout)
        self.layout.addLayout(button_v_layout)
        self.layout.addStretch(1)

        member_hidden = self.member_config.get('group.hide_bubbles', False)

        show_hidden = workflow.config.get('config', {}).get('show_hidden_bubbles', False)
        show_nested = workflow.config.get('config', {}).get('show_nested_bubbles', False)
        if self.member_id.count('.') > 0 and not show_nested:
            self.hide()
        if member_hidden and not show_hidden:
            self.hide()

        self.bubble.append_text(message.content)

    def view_log(self, _):
        if not self.bubble.log:
            return

        pretty_json = json.dumps(self.bubble.log, indent=4)

        log_window = QMainWindow()
        log_window.setWindowTitle('Message Input')
        log_window.setFixedSize(400, 750)

        text_edit = QTextEdit(text=pretty_json)

        log_window.setCentralWidget(text_edit)

        # Show the new window
        log_window.show()
        self.log_windows.append(log_window)

    def enterEvent(self, event):
        self.check_and_toggle_buttons()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.check_and_toggle_buttons()
        super().leaveEvent(event)

    def check_and_toggle_buttons(self):
        # For each class defined in self.bubble where ap_message_button is set
        buttons = [
            getattr(self, attr) for attr in dir(self)
            if hasattr(getattr(self, attr), '_ap_message_button')
        ]

        try:
            is_under_mouse = self.underMouse()
            for btn in buttons:
                btn.setVisible(is_under_mouse)
            if hasattr(self, 'btn_countdown'):
                self.btn_countdown.reset_countdown()
        except RuntimeError:
            pass

    def check_to_start_a_branch(self, role, new_message, member_id):
        workflow = self.parent.workflow
        last_msg = workflow.message_history.messages[-1]
        is_last_msg = last_msg.id == self.bubble.msg_id
        if not is_last_msg:
            self.start_new_branch()
            workflow.save_message(role, new_message, member_id)

    def start_new_branch(self):
        branch_msg_id = self.branch_msg_id
        editing_msg_id = self.bubble.msg_id

        # Delete all messages from editing bubble onwards
        self.parent.delete_messages_since(editing_msg_id)

        # Create a new leaf context
        sql.execute("""
           INSERT INTO contexts (kind, parent_id, branch_msg_id)
            SELECT
				c.kind,
				cm.context_id,
				cm.id
			FROM contexts_messages cm
			LEFT JOIN contexts c
				ON cm.context_id = c.id
			WHERE cm.id = ?
        """, (branch_msg_id,))
        new_leaf_id = sql.get_scalar('SELECT MAX(id) FROM contexts')
        self.parent.workflow.leaf_id = new_leaf_id

    class CountdownButton(QPushButton):
        def __init__(self, parent, target_button):
            super().__init__(parent=parent)
            self.main = find_main_widget(self)
            self.parent = parent
            self.target_button = target_button
            self.countdown_from = 5
            self.countdown = 5
            self.countdown_stopped = False
            self.setIcon(QIcon())  # Initially, set an empty icon
            self.setFixedSize(22, 22)
            self.clicked.connect(self.on_clicked)
            self.timer = QTimer(self)
            self.hide()

        def start_timer(self, secs=5):
            if self.countdown_stopped:
                return
            self.countdown_from = secs
            self.countdown = secs
            self.show()
            self.setText(f"{self.countdown}")

            self.timer.timeout.connect(self.update_countdown)
            self.timer.start(1000)  # Start countdown timer with 1-second interval

        def enterEvent(self, event):
            close_pixmap = colorize_pixmap(QPixmap(":/resources/close.png"))
            icon = QIcon(close_pixmap)
            self.setIcon(icon)
            self.setIconSize(QSize(10, 10))
            self.setText("")  # Clear the text when displaying the icon
            self.reset_countdown()
            super().enterEvent(event)

        def leaveEvent(self, event):
            self.setIcon(QIcon())  # Clear the icon
            self.setText(str(self.countdown))
            self.reset_countdown()
            super().leaveEvent(event)

        def on_clicked(self):
            self.countdown_stopped = True
            self.hide()

        def update_countdown(self):
            if not self.isVisible():
                return

            if self.countdown > 0:
                self.countdown -= 1
                self.setText(f"{self.countdown}")
            else:
                self.timer.stop()
                self.countdown_stopped = True
                self.target_button.click()
                self.hide()

        def reset_countdown(self):
            if self.countdown_stopped:
                return
            self.timer.stop()
            self.countdown = self.countdown_from
            self.setText(f"{self.countdown}")

            if not self.parent.underMouse():
                self.timer.start(1000)  # Restart the timer

class MessageBubble(QTextEdit):
    def __init__(self, parent, message, **kwargs):
        super().__init__(parent=parent)
        self.main = parent.parent.main
        self.parent = parent
        self.msg_id: int = None
        self.member_id: str = None

        self.role: str = None
        self.log = None

        self.text = ''
        self.code_blocks = []

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )
        self.setWordWrapMode(QTextOption.WordWrap)

        self.enable_markdown: bool = True

        self.readonly = kwargs.get('readonly', True)
        self.is_edit_mode = False
        self.textChanged.connect(self.on_text_edited)

        self.installEventFilter(self)

        self.workflow = self.parent.parent.workflow
        self.branch_entry = {}
        self.has_branches = False

        self.autorun_button = kwargs.get('autorun_button', None)
        self.autorun_secs = kwargs.get('autorun_secs', 5)

        self.set_message(message)

    def set_message(self, message):
        self.msg_id = message.id
        self.member_id = message.member_id

        self.role = message.role
        self.log = message.log
        self.text = ''
        self.code_blocks = []

        self.enable_markdown = self.parent.member_config.get('chat.display_markdown', True)
        if self.readonly:  # role not in ('user', 'code'):
            self.setReadOnly(True)

        branches = self.workflow.message_history.branches
        self.branch_entry = {k: v for k, v in branches.items() if self.msg_id == k or self.msg_id in v}
        self.has_branches = len(self.branch_entry) > 0

        if self.has_branches:
            self.branch_buttons = self.BubbleBranchButtons(self.branch_entry, parent=self)
            self.branch_buttons.hide()

        role_config = self.main.system.roles.get_role_config(self.role)
        bg_color = role_config.get('bubble_bg_color', '#252427')
        text_color = role_config.get('bubble_text_color', '#999999')
        self.setStyleSheet(f"background-color: {bg_color}; color: {text_color};")

    def extract_code_blocks(self, text):
        """Extracts code blocks, their first and last line number, and their language from a block of text"""
        import re

        # Regular expression to match code blocks, with or without language
        code_block_re = re.compile(r'```(?P<lang>\w+)?\n?(?P<code>.*?)```', re.DOTALL)

        # Find all code blocks in the text
        matches = list(code_block_re.finditer(text))

        # Initialize an empty list to hold the results
        code_blocks_with_line_numbers = []

        for match in matches:
            start_pos = match.start()  # Starting position of the code block
            end_pos = match.end()  # Ending position of the code block
            lang = match.group('lang')  # Language of the code block
            code = match.group('code')  # Code block content

            # Calculate the line number of the start and end of the code block
            start_line_number = text[:start_pos].count('\n') + 1
            end_line_number = text[:end_pos].count('\n')

            # Append the (language, code, start line number, end line number) tuple to the result list
            code_blocks_with_line_numbers.append((lang if lang else None, code, start_line_number, end_line_number))

        return code_blocks_with_line_numbers

    def on_text_edited(self):
        self.updateGeometry()
        # self.update_size()

    def get_code_block_under_cursor(self, cursor_pos):
        if not self.code_blocks:
            return None
        cursor = self.cursorForPosition(cursor_pos)
        line_number = cursor.blockNumber() + 1
        for lang, code, start_line_number, end_line_number in self.code_blocks:
            if start_line_number <= line_number < end_line_number:
                return lang, code, start_line_number, end_line_number
            line_number += 2
        return None

    def enterEvent(self, event):
        super().enterEvent(event)
        if self.has_branches:
            self.branch_buttons.reposition()
            self.branch_buttons.show()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self.has_branches:
            self.branch_buttons.hide()

    def focusOutEvent(self, event):
        self.toggle_edit_mode(False)
        super().focusOutEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            can_edit = not self.isReadOnly()
            if can_edit:
                self.toggle_edit_mode(True)

            cursor = self.cursorForPosition(event.pos())
            if cursor.charFormat().isAnchor():
                link = cursor.charFormat().anchorHref()
                QDesktopServices.openUrl(QUrl(link))
                return

        super().mousePressEvent(event)

    def toggle_edit_mode(self, state):
        if self.is_edit_mode == state:
            return
        should_reset_text = self.is_edit_mode != state
        self.is_edit_mode = state
        if not self.is_edit_mode:  # Save the text
            self.text = self.toPlainText()
        if should_reset_text:
            self.setMarkdownText(self.text)

    def setMarkdownText(self, text):
        self.text = text
        cursor = self.textCursor()

        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        system_config = self.parent.parent.main.system.config.dict
        font = system_config.get('display.text_font', '')
        size = system_config.get('display.text_size', 15)

        cursor = self.textCursor()  # Get the current QTextCursor
        cursor_position = cursor.position()  # Save the current cursor position
        anchor_position = cursor.anchor()  # Save the anchor position for selection

        role_config = self.main.system.roles.get_role_config(self.role)

        bubble_text_color = role_config.get('bubble_text_color', '#d1d1d1')

        code_color = '#919191' if self.role != 'code' else bubble_text_color
        css_background = f"code {{ color: {code_color}; }}"
        css_font = f"body {{ color: {bubble_text_color}; font-family: {font}; font-size: {size}px; white-space: pre-wrap; }}"
        css = f"{css_background}\n{css_font}"

        if self.enable_markdown and not self.is_edit_mode:
            text = mistune.markdown(text)
            # text = text.replace('\n</code>', '</code>')  # !! #
            html = f"<style>{css}</style><body>{text}</body>"
            self.setHtml(html)
        else:
            self.setPlainText(text)

        # Restore the cursor position and selection
        new_cursor = QTextCursor(self.document())  # New cursor from the updated document
        new_cursor.setPosition(anchor_position)  # Set the start of the selection
        new_cursor.setPosition(cursor_position, QTextCursor.KeepAnchor)  # Set the end of the selection
        self.setTextCursor(new_cursor)  # Apply the new cursor with the restored position and selection

        # cursor.setPosition(start, cursor.MoveAnchor)
        # cursor.setPosition(end, cursor.KeepAnchor)
        # self.setTextCursor(cursor)
        self.code_blocks = self.extract_code_blocks(text)
        # self.update_size()

    def calculate_button_position(self):
        button_width = 32
        button_height = 32
        button_x = self.width() - button_width
        button_y = self.height() - button_height
        return QRect(button_x, button_y, button_width, button_height)

    def append_text(self, text):
        # cursor = self.textCursor()
        #
        # start = cursor.selectionStart()
        # end = cursor.selectionEnd()

        self.text += text
        # self.original_text = self.text
        self.setMarkdownText(self.text)
        # self.update_size()
        #
        # cursor.setPosition(start, cursor.MoveAnchor)
        # cursor.setPosition(end, cursor.KeepAnchor)
        #
        # self.setTextCursor(cursor)
        # self.code_blocks = self.extract_code_blocks(text)

    def sizeHint(self):
        doc = self.document().clone()
        main = find_main_widget(self)
        page_chat = main.page_chat
        sidebar = main.main_menu.settings_sidebar
        doc.setTextWidth(page_chat.width() - sidebar.width())
        lr = self.contentsMargins().left() + self.contentsMargins().right() + 6
        doc_width = doc.idealWidth() + lr
        doc_height = doc.size().height() # + self.contentsMargins().top() + self.contentsMargins().bottom()
        return QSize(doc_width, doc_height)

    def minimumSizeHint(self):
        return QSize(0, self.sizeHint().height())

    def contextMenuEvent(self, event):
        # add all default items
        menu = self.createStandardContextMenu()

        menu.addSeparator()
        # delete_action = menu.addAction("Add message after")
        # delete_action.triggered.connect(self.add_msg_after)

        delete_action = menu.addAction("Delete message")
        delete_action.triggered.connect(self.delete_message)

        search_action = menu.addAction("Search the web")
        search_action.triggered.connect(self.search_web)

        over_code_block = self.get_code_block_under_cursor(event.pos())
        if over_code_block:
            menu.addSeparator()

            lang, code, start_line_number, end_line_number = over_code_block
            copy_code_action = menu.addAction("Copy code block")
            copy_code_action.triggered.connect(lambda: QApplication.clipboard().setText(code))

        if self.log:
            menu.addSeparator()
            view_log_action = menu.addAction("View log")
            view_log_action.triggered.connect(self.view_log)

            if 'member_id' in self.log and find_workflow_widget(self):
                view_member_action = menu.addAction("Goto member")
                view_member_action.triggered.connect(self.goto_member)

        #     edit_action = menu.addAction("Edit message")
        #     edit_action.triggered.connect(self.edit_message)

        # show context menu
        menu.exec_(event.globalPos())

    def view_log(self):
        self.parent.view_log(None)

    def goto_member(self):
        full_member_id = self.log.get('member_id')
        workflow_settings = find_workflow_widget(self)
        workflow_settings.goto_member(full_member_id)
        main = find_main_widget(self)
        if main:
            page_chat = main.page_chat
            if not page_chat.workflow_settings.isVisible():
                page_chat.top_bar.agent_name_clicked(None)

    def search_web(self):
        search_text = self.textCursor().selectedText()
        if search_text == '':
            search_text = self.toPlainText()
        formatted_text = quote(search_text)
        QDesktopServices.openUrl(QUrl(f"https://www.google.com/search?q={formatted_text}"))

    def delete_message(self):
        if self.msg_id == -1:
            display_message(self,
                message="Please wait for response to finish before deleting",
                icon=QMessageBox.Warning,
            )
            return

        if getattr(self, 'has_branches', False):
            display_message(self,
                message="This message has branches, deleting is not implemented yet",
                icon=QMessageBox.Warning,
            )
            return

        retval = display_message_box(
            icon=QMessageBox.Question,
            title="Delete message",
            text="Are you sure you want to delete this message?",
            buttons=QMessageBox.Yes | QMessageBox.No
        )
        if retval != QMessageBox.Yes:
            return

        sql.execute("DELETE FROM contexts_messages WHERE id = ?;", (self.msg_id,))
        self.main.page_chat.load()

    class BubbleBranchButtons(QWidget):
        def __init__(self, branch_entry, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.main = parent.main
            message_bubble = self.parent
            self.bubble_id = message_bubble.msg_id

            self.btn_back = QPushButton("🠈" if not platform.system() == 'Darwin' else "<", self)
            self.btn_next = QPushButton("🠊" if not platform.system() == 'Darwin' else ">", self)
            self.btn_back.setFixedSize(30, 12)
            self.btn_next.setFixedSize(30, 12)
            self.btn_next.setProperty("class", "branch-buttons")
            self.btn_back.setProperty("class", "branch-buttons")

            self.reposition()

            self.branch_entry = branch_entry
            branch_root_msg_id = next(iter(branch_entry))
            self.child_branches = branch_entry[branch_root_msg_id]

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
                self.main.page_chat.workflow.deactivate_all_branches_with_msg(self.bubble_id)
                current_index = self.child_branches.index(self.bubble_id)
                if current_index == 0:
                    self.reload_following_bubbles()
                    return
                next_msg_id = self.child_branches[current_index - 1]
                self.main.page_chat.workflow.activate_branch_with_msg(next_msg_id)

            self.reload_following_bubbles()

        def next(self):
            if self.bubble_id in self.branch_entry:
                activate_msg_id = self.child_branches[0]
                # self.main.page_chat.workflow.deactivate_all_branches_with_msg(self.bubble_id) # !! #
                self.main.page_chat.workflow.activate_branch_with_msg(activate_msg_id)
            else:
                current_index = self.child_branches.index(self.bubble_id)
                if current_index == len(self.child_branches) - 1:
                    return
                self.main.page_chat.workflow.deactivate_all_branches_with_msg(self.bubble_id)
                next_msg_id = self.child_branches[current_index + 1]
                self.main.page_chat.workflow.activate_branch_with_msg(next_msg_id)

            self.reload_following_bubbles()

        def reload_following_bubbles(self):
            self.main.page_chat.message_collection.delete_messages_since(self.bubble_id)
            self.main.page_chat.workflow.message_history.load()
            self.main.page_chat.message_collection.refresh()

        def update_buttons(self):
            pass


class MessageButton(IconButton):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent, **kwargs)
        self.msg_container = parent
        self.setFixedSize(32, 24)
        self.hide()
        if hasattr(self, 'on_clicked'):
            self.pressed.connect(self.on_clicked)  # CANT USE CLICKED


class UserBubble(MessageBubble):
    def __init__(self, parent, message):
        super().__init__(
            parent=parent,
            message=message,
            readonly=False,
        )

    @message_button('btn_resend')
    class ResendButton(MessageButton):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             icon_path=':/resources/icon-send.png')

        def on_clicked(self):
            if self.msg_container.parent.workflow.responding:
                return
            msg_to_send = self.msg_container.bubble.text
            if msg_to_send == '':
                return

            self.msg_container.start_new_branch()

            # Finally send the message like normal
            run_workflow = self.msg_container.parent.workflow.config.get('config', {}).get('autorun', True)
            editing_member_id = self.msg_container.member_id
            self.msg_container.parent.send_message(msg_to_send, clear_input=False, as_member_id=editing_member_id, run_workflow=run_workflow)


class AssistantBubble(MessageBubble):
    def __init__(self, parent, message):
        super().__init__(parent=parent, message=message)


class CodeBubble(MessageBubble):
    def __init__(self, parent, message):
        super().__init__(
            parent=parent,
            message=message,
            readonly=False,
            autorun_button='btn_rerun',
            autorun_secs=5,
        )

    @message_button('btn_rerun')
    class RerunButton(MessageButton):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             icon_path=':/resources/icon-run-solid.png')

        def on_clicked(self):
            if self.msg_container.parent.workflow.responding:
                return
            # self.msg_container.btn_countdown.hide()

            bubble = self.msg_container.bubble
            member_id = self.msg_container.member_id
            lang, code = split_lang_and_code(bubble.text)
            code = bubble.toPlainText()

            self.msg_container.check_to_start_a_branch(
                role=bubble.role,
                new_message=f'```{lang}\n{code}\n```',
                member_id=member_id
            )

            oi_res = interpreter.computer.run(lang, code)
            output = next(r for r in oi_res if r['format'] == 'output').get('content', '')
            self.msg_container.parent.send_message(output, role='output', as_member_id=member_id, feed_back=True, clear_input=False)


class ToolBubble(MessageBubble):
    def __init__(self, parent, message):
        super().__init__(
            parent=parent,
            message=message,
            autorun_button='btn_rerun',
            autorun_secs=5,
        )

    def setMarkdownText(self, text):
        text = get_json_value(text, 'text', 'Error parsing tool')
        super().setMarkdownText(text)

    @message_extension('tool_params')
    class ToolParams(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent)
            from src.system.base import manager
            parsed, config = try_parse_json(parent.message.content)
            if not parsed:
                return
            tool_schema = manager.tools.get_param_schema(config['tool_uuid'])
            self.config: Dict[str, Any] = json.loads(config.get('args', '{}'))
            self.schema = tool_schema
            self.build_schema()
            self.load()

    @message_button('btn_rerun')
    class RerunButton(MessageButton):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             icon_path=':/resources/icon-run-solid.png')

        def on_clicked(self):
            if self.msg_container.parent.workflow.responding:
                return
            # self.msg_container.btn_countdown.hide()

            bubble = self.msg_container.bubble
            member_id = self.msg_container.member_id
            parsed, tool_dict = try_parse_json(bubble.text)
            if not parsed:
                return

            tool_uuid = tool_dict.get('tool_uuid', None)
            tool_params_widget = self.msg_container.tool_params
            tool_args = tool_params_widget.get_config()
            tool_dict['args'] = json.dumps(tool_args)

            self.msg_container.check_to_start_a_branch(
                role=bubble.role,
                new_message=json.dumps(tool_dict),
                member_id=member_id
            )

            from src.system.base import manager
            result = manager.tools.compute_tool(tool_uuid, tool_args)
            tmp = json.loads(result)
            tmp['tool_call_id'] = tool_dict.get('tool_call_id', None)
            result = json.dumps(tmp)
            self.msg_container.parent.send_message(result, role='result', as_member_id=member_id, feed_back=True, clear_input=False)

    @message_button('btn_goto_tool')
    class GotoToolButton(MessageButton):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             icon_path=':/resources/icon-tool-small.png')
            content = self.msg_container.message.content
            self.tool_id = get_json_value(content, 'tool_uuid')
            if not self.tool_id:
                self.hide()

        def on_clicked(self):  # todo dupe code
            from src.gui.widgets import find_main_widget
            main = find_main_widget(self)
            main.main_menu.settings_sidebar.page_buttons['Tools'].click()
            tools_tree = main.main_menu.pages['Tools'].tree
            # select the tool
            for i in range(tools_tree.topLevelItemCount()):
                row_uuid = tools_tree.topLevelItem(i).text(2)
                if row_uuid == self.tool_id:
                    tools_tree.setCurrentItem(tools_tree.topLevelItem(i))


class ResultBubble(MessageBubble):
    def __init__(self, parent, message):
        super().__init__(
            parent=parent,
            message=message,
        )

    def setMarkdownText(self, text):
        text = get_json_value(text, 'output', 'Error parsing result')
        super().setMarkdownText(text)


class ImageBubble(MessageBubble):
    def __init__(self, parent, message):
        super().__init__(
            parent=parent,
            message=message,
        )
        self.image = None
        self.zoomed = False

    def setMarkdownText(self, text):
        self.text = text
        filepath = get_json_value(text, 'filepath')
        url = get_json_value(text, 'url')

        if not url and filepath:
            try:
                self.image = QImage(filepath)
                if self.image.isNull():
                    raise Exception("Invalid image")

                self.update_image_display()
            except Exception as e:
                print(f"Error reading image file: {e}")
                self.setPlainText(f"Error loading image: {filepath}")
        else:
            self.setPlainText(f"No valid image path or URL provided")

    def update_image_display(self):
        if self.image:
            self.document().clear()

            w, h = self.image.width(), self.image.height()
            size = max(w, h) if self.zoomed else 250
            scaled_image = self.image.scaled(
                size, size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            doc = self.document()
            doc.addResource(QTextDocument.ImageResource, QUrl("image"), scaled_image)

            cursor = QTextCursor(doc)
            cursor.insertImage("image")

            self.updateGeometry()
        else:
            self.setPlainText(f"Error loading image: {get_json_value(self.text, 'filepath', 'Unknown')}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.zoomed = not self.zoomed
            self.update_image_display()


class AudioBubble(MessageBubble):
    def __init__(self, parent, message):
        super().__init__(
            parent=parent,
            message=message,
            readonly=True,
        )

    def setMarkdownText(self, text):
        filepath = get_json_value(text, 'filepath', 'Error parsing audio')
        filename = os.path.basename(filepath)
        super().setMarkdownText(filename)

    @message_button('btn_play')
    class PlayButton(MessageButton):
        def __init__(self, parent):
            super().__init__(parent=parent,
                             icon_path=':/resources/icon-run-solid.png')

        def on_clicked(self):
            content = self.msg_container.message.content
            filepath = get_json_value(content, 'filepath', 'Error parsing audio')
            play_file(filepath)



def get_json_value(json_str, key, default=None):
    """Get a value from a JSON string by key"""
    try:
        data = json.loads(json_str)
        return data.get(key, default)
    except json.JSONDecodeError:
        return default
