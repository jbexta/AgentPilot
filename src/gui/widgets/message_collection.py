
import asyncio
import json
import os
from typing import Optional, List, Dict, Tuple, Any

from PySide6.QtWidgets import *
from PySide6.QtCore import QSize, QTimer, QRect, QEvent, Slot, QRunnable, QPropertyAnimation, \
    QEasingCurve
from PySide6.QtGui import QPixmap, QIcon, Qt

from src.gui.bubbles import MessageBubble
from src.gui.util import colorize_pixmap, IconButton, find_main_widget, clear_layout, \
    ToggleIconButton, CHBoxLayout, CVBoxLayout, safe_single_shot

from src.system import manager

from src.utils.helpers import get_member_name_from_config, try_parse_json, \
    display_message, block_signals, get_avatar_paths_from_config, \
    path_to_pixmap, apply_alpha_to_hex, set_module_type
from src.utils import sql


@set_module_type(module_type='Widgets')
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
        bubble_spacing = manager.config.get('display.bubble_spacing', 5)
        self.chat_scroll_layout.setSpacing(bubble_spacing)
        self.chat_scroll_layout.addStretch(1)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidget(self.chat_widget)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.verticalScrollBar().rangeChanged.connect(self.maybe_scroll_to_end)
        self.coupled_scroll = True

        self.layout.addWidget(self.scroll_area)
        self.scroll_animation = QPropertyAnimation(self.scroll_area.verticalScrollBar(), b"value")

        self.waiting_for_bar = self.WaitingForBar(self)
        self.layout.addWidget(self.waiting_for_bar)
        self.scroll_to_end()

    def maybe_scroll_to_end(self):
        scroll_bar = self.scroll_area.verticalScrollBar()
        is_at_bottom = scroll_bar.value() >= scroll_bar.maximum() - 50
        if is_at_bottom:
            safe_single_shot(50, lambda: self.scroll_to_end())

    def scroll_to_end(self):
        scroll_bar = self.scroll_area.verticalScrollBar()

        if self.scroll_animation.state() == QPropertyAnimation.Running:
            self.scroll_animation.stop()

        self.scroll_animation.setDuration(100)
        self.scroll_animation.setStartValue(scroll_bar.value())
        self.scroll_animation.setEndValue(scroll_bar.maximum())
        self.scroll_animation.setEasingCurve(QEasingCurve.Linear)
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
                self.chat_bubbles[i].check_and_toggle_collapse_button()
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

            self.last_member_bubbles.clear()

            self.waiting_for_bar.load()
            if self.parent.__class__.__name__ == 'Page_Chat':
                self.parent.top_bar.load()

    def insert_bubble(self, message=None):
        from src.system import manager
        show_bubble = manager.roles.get(message.role, {}).get('show_bubble', True)
        if not show_bubble:
            return

        msg_container = MessageContainer(self, message=message)
        bubble = msg_container.bubble
        index = len(self.chat_bubbles)
        # last_bubble = self.chat_bubbles[-1] if self.chat_bubbles else None
        # if last_bubble:
        #     last_bubble.check_and_toggle_buttons()
        self.chat_bubbles.insert(index, msg_container)
        self.chat_scroll_layout.insertWidget(index, msg_container)
        self.last_member_bubbles[(bubble.role, bubble.member_id)] = self.chat_bubbles[-1]
        # msg_container.check_and_toggle_buttons()
        # last_index = index - 1

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

    def send_message(
        self,
        message: str,
        role: str = 'user',
        as_member_id: str = None,  # '1',
        feed_back=False,
        clear_input=False,
        run_workflow=True,
        alt_turn=None,
    ):  # todo default as_mem_id
        if self.main.chat_threadpool.activeThreadCount() > 0:
            return

        toggle_alt_turn = False
        members = self.workflow.members
        workflow_first_member = next(iter(members.values()), None)
        if not workflow_first_member:
            return
        if as_member_id is None:
            as_member_id = workflow_first_member.member_id

        last_msg = self.workflow.message_history.messages[-1] if self.workflow.message_history.messages else None
        if as_member_id == workflow_first_member.member_id and last_msg:
            toggle_alt_turn = True

        if alt_turn:
            self.workflow.message_history.alt_turn_state = alt_turn
        elif toggle_alt_turn:
            state = self.workflow.message_history.alt_turn_state
            self.workflow.message_history.alt_turn_state = 1 - state

        new_msg = self.workflow.save_message(role, message, member_id=as_member_id)
        if not new_msg:
            return

        if clear_input:
            self.main.message_text.clear()
            self.main.message_text.setFixedHeight(51)
            self.main.send_button.setFixedHeight(51)

        self.workflow.message_history.load_branches()
        self.refresh(block_autorun=True)

        # if last_msg:
        #     # Collapse button
        #     last_bubble = self.chat_bubbles[-2]
        #     last_bubble.check_and_toggle_buttons()

        if role == 'result':
            parsed, res_dict = try_parse_json(message)
            if not parsed or res_dict.get('status') == 'error':
                run_workflow = False

        scroll_bar = self.scroll_area.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())

        self.refresh_waiting_bar()
        self.parent.workflow_settings.refresh_member_highlights()
        safe_single_shot(5, lambda: self.scroll_to_end())

        if run_workflow:
            self.run_workflow(from_member_id=as_member_id, feed_back=feed_back)

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
        # print('new_sentence', role, member_id, sentence)
        with self.workflow.message_history.thread_lock:
            if (role, member_id) not in self.last_member_bubbles:
                from src.utils.messages import Message
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
        # with self.workflow.message_history.thread_lock:
        #     self.last_member_bubbles.clear()
        self.workflow.responding = False
        self.main.send_button.update_icon(is_generating=False)

        self.refresh_waiting_bar(set_visibility=True)
        self.parent.workflow_settings.refresh_member_highlights()

    def refresh_waiting_bar(self, set_visibility=None):
        """Optionally use set_visibility to show or hide, while respecting the system config"""
        from src.system import manager
        workflow_is_multi_member = self.workflow.count_members() > 1
        show_waiting_bar_when = manager.config.get('display.show_waiting_bar', 'In Group')
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for container in self.chat_bubbles:
            container.bubble.updateGeometry()


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

        from src.utils.messages import Message
        self.bubble: MessageBubble = None
        self.branch_msg_id: int = None
        self.child_branches = None
        self.message: Message = None

        self.profile_pic_label = None
        self.member_name_label = None
        self.collapse_button = None

        self.fade_overlay = QWidget(self)
        self.fade_height = 75
        self.fade_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.fade_overlay.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.fade_overlay.hide()

        with block_signals(self):
            self.load_message(message)

    def load_message(self, message):
        clear_layout(self.layout)

        workflow = self.parent.workflow
        self.member_id = message.member_id
        member = workflow.members.get(self.member_id, None)
        self.member_config = getattr(member, 'config') if member else {}
        self.message = message

        from src.system import manager
        config = manager.config
        msg_role_config = manager.roles.get(message.role, {})
        role_module = msg_role_config.get('module', 'MessageBubble')

        from src.gui.bubbles import MessageBubble
        bubble_class = manager.modules.get_module_class(
            module_type='Bubbles',
            module_name=role_module,
            default=MessageBubble,
        )
        self.bubble = bubble_class(parent=self, message=message)

        context_is_multi_member = workflow.count_members() > 1
        show_avatar_when = config.get('display.show_bubble_avatar', 'In Group')
        show_name_when = config.get('display.show_bubble_name', 'In Group')
        show_avatar = (show_avatar_when == 'In Group' and context_is_multi_member) or show_avatar_when == 'Always'
        show_name = (show_name_when == 'In Group' and context_is_multi_member) or show_name_when == 'Always'

        if show_avatar:
            agent_avatar_path = get_avatar_paths_from_config(member.config if member else {})
            diameter = msg_role_config.get(
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
                user_config = manager.roles.get('user', {})
                user_bubble_bg_color = user_config.get('bubble_bg_color', '#ff11121b')
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

        self.collapse_button = ToggleIconButton(
            parent=self,
            icon_path=':/resources/icon-left-arrow.png',
            icon_path_checked=':/resources/icon-expanded.png',
            target=self.toggle_collapse,
            tooltip='Collapse',
            tooltip_checked='Expand',
        )
        # connect to toggle_collapse
        self.collapse_button.setFixedSize(32, 24)
        button_v_layout.addWidget(self.collapse_button)
        button_v_layout.addStretch(1)

        # get all class definitions in bubble_class decorated with @message_bubble
        bubble_buttons = {
            name: cls for name, cls in self.bubble.__dict__.items()
            if hasattr(cls, '_ap_message_button') and isinstance(cls, type)
        }
        bubble_extensions = {
            name: cls for name, cls in bubble_class.__dict__.items()
            if hasattr(cls, '_ap_message_extension') and isinstance(cls, type)
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

    def toggle_collapse(self):
        self.bubble.collapsed = not self.bubble.collapsed
        app_height = self.parent.main.size().height()
        from src.system import manager
        collapse_ratio = manager.config.get('display.collapse_ratio', 0.5)
        too_big_height = collapse_ratio * app_height
        self.bubble.setMaximumHeight(too_big_height if self.bubble.collapsed else 16777215)
        if hasattr(self, 'update_fade_effect'):
            self.update_fade_effect()
        self.collapse_button.setChecked(self.bubble.collapsed)

    def update_fade_effect(self):
        if not self.bubble.collapsed:
            self.fade_overlay.hide()
            return

        fade_h = min(self.fade_height, self.height())
        if fade_h <= 0:
             self.fade_overlay.hide()
             return

        overlay_rect = QRect(
            0,                    # x = start from left edge
            self.height() - fade_h, # y = position top of overlay 'fade_h' pixels from bottom
            self.width(),         # width = full width of bubble
            fade_h                # height = the fade height
        )
        self.fade_overlay.setGeometry(overlay_rect)

        from src.system import manager
        bg_color = manager.config.get('display.primary_color', '#ff11121b')
        gradient_style = f"""
            background-color: qlineargradient(
                spread:pad, x1:0, y1:0, x2:0, y2:0.9,
                stop:0 rgba(0, 0, 0, 0),
                stop:1 {bg_color}
            );
            border-radius: 10px;
        """
        self.fade_overlay.setStyleSheet(gradient_style)

        self.fade_overlay.raise_()
        self.fade_overlay.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_fade_effect()

    def enterEvent(self, event):
        self.check_and_toggle_buttons()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.check_and_toggle_buttons()
        self.check_and_toggle_collapse_button()
        super().leaveEvent(event)

    def check_and_toggle_buttons(self):
        # For each class instance in self where _ap_message_button is set
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

    def check_and_toggle_collapse_button(self):
        if hasattr(self, 'collapse_button'):
            from src.system import manager
            enable_collapse = manager.config.get('display.collapse_large_bubbles', True)

            if not enable_collapse:
                self.collapse_button.setVisible(False)
                return

            from src.system import manager
            collapse_ratio = manager.config.get('display.collapse_ratio', 0.5)
            height = self.bubble.sizeHint().height()
            app_height = self.parent.main.size().height()
            too_big = height / app_height > collapse_ratio

            bubbles = self.parent.chat_bubbles
            last_bubble_id = bubbles[-1].bubble.msg_id if bubbles else None
            # container_is_last = self.parent.chat_bubbles[-1].bubble.msg_id == self if self.parent.chat_bubbles else True  # (self not in self.parent.chat_bubbles) or last_bubble_id == self.bubble.msg_id
            last_message = self.parent.workflow.message_history.last()  # todo hacky, rewrite bubbles
            last_message_id = last_message['id'] if last_message else None
            container_is_last = self.bubble.msg_id == -1 or self.bubble.msg_id == last_message_id
            self.collapse_button.setVisible(too_big)  # is_under_mouse and too_big)
            if too_big and not self.bubble.collapsed and not container_is_last and not self.bubble.is_edit_mode:
                self.collapse_button.click()
            else:
                pass

    def check_to_start_a_branch(self, role, new_message, member_id):
        workflow = self.parent.workflow
        last_msg = workflow.message_history.messages[-1]
        is_last_msg = last_msg.id == self.bubble.msg_id
        if not is_last_msg:
            self.start_new_branch()
            # ~~ #
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