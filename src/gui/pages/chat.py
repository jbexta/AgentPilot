import asyncio
import json
import os
import queue
import sqlite3

from PySide6.QtWidgets import *
from PySide6.QtCore import QThreadPool, QEvent, QTimer, QRunnable, Slot, QFileInfo, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import Qt, QIcon, QPixmap

from src.members.workflow import WorkflowSettings
from src.utils.helpers import path_to_pixmap, display_messagebox, block_signals, get_avatar_paths_from_config, \
    get_member_name_from_config, merge_config_into_workflow_config, apply_alpha_to_hex, convert_model_json_to_obj
from src.utils import sql

from src.utils.messages import Message

from src.members.workflow import Workflow
from src.gui.bubbles import MessageContainer
from src.gui.widgets import IconButton, clear_layout
from src.gui.config import CHBoxLayout, CVBoxLayout


class Page_Chat(QWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)

        self.main = parent  # .parent
        self.icon_path = ':/resources/icon-chat.png'
        self.workspace_window = None

        latest_context = sql.get_scalar('SELECT id FROM contexts WHERE parent_id IS NULL ORDER BY id DESC LIMIT 1')
        if latest_context:
            latest_id = latest_context
        else:
            # # make new context
            config_json = json.dumps({
                '_TYPE': 'workflow',
                'members': [
                    {'id': 1, 'agent_id': None, 'loc_x': -10, 'loc_y': 64, 'config': {'_TYPE': 'user'}, 'del': 0},
                    {'id': 2, 'agent_id': 0, 'loc_x': 37, 'loc_y': 30, 'config': {}, 'del': 0}
                ],
                'inputs': [],
            })
            sql.execute("INSERT INTO contexts (config) VALUES (?)", (config_json,))
            c_id = sql.get_scalar('SELECT id FROM contexts ORDER BY id DESC LIMIT 1')
            latest_id = c_id

        self.workflow = Workflow(main=self.main, context_id=latest_id)

        self.threadpool = QThreadPool()
        self.chat_bubbles = []
        self.last_member_bubbles = {}

        self.layout = CVBoxLayout(self)

        self.top_bar = self.Top_Bar(self)
        self.layout.addWidget(self.top_bar)

        self.workflow_settings = self.ChatWorkflowSettings(self)
        self.workflow_settings.hide()
        self.layout.addWidget(self.workflow_settings)

        self.scroll_area = QScrollArea(self)
        self.chat = QWidget(self.scroll_area)
        self.chat_scroll_layout = CVBoxLayout(self.chat)
        bubble_spacing = self.main.system.config.dict.get('display.bubble_spacing', 5)
        self.chat_scroll_layout.setSpacing(bubble_spacing)
        self.chat_scroll_layout.addStretch(1)

        self.scroll_area.setWidget(self.chat)
        self.scroll_area.setWidgetResizable(True)

        self.animation_queue = queue.Queue()
        self.running_animation = None

        self.layout.addWidget(self.scroll_area)

        self.waiting_for_bar = self.WaitingForBar(self)
        self.layout.addWidget(self.waiting_for_bar)

        self.attachment_bar = self.AttachmentBar(self)
        self.layout.addWidget(self.attachment_bar)

        self.installEventFilterRecursively(self)
        self.temp_text_size = None
        self.decoupled_scroll = False

        self.show_hidden_messages = False
        # self.open_workspace()

    def load(self, also_config=True):
        self.clear_bubbles()
        self.workflow.load()
        if also_config:
            self.workflow_settings.load_config(self.workflow.config)
            self.workflow_settings.load()
        self.refresh()
        self.refresh_waiting_bar()

    def refresh(self):
        with self.workflow.message_history.thread_lock:
            # Disable updates
            self.setUpdatesEnabled(False)
            # get scroll position
            scroll_bar = self.scroll_area.verticalScrollBar()
            scroll_pos = scroll_bar.value()

            # iterate chat_bubbles backwards and remove any that have id = -1
            for i in range(len(self.chat_bubbles) - 1, -1, -1):
                if self.chat_bubbles[i].bubble.msg_id == -1:
                    bubble_container = self.chat_bubbles.pop(i)
                    self.chat_scroll_layout.removeWidget(bubble_container)
                    bubble_container.hide()  # deleteLater()

            last_container = self.chat_bubbles[-1] if self.chat_bubbles else None
            last_bubble_msg_id = last_container.bubble.msg_id if last_container else 0

            for msg in self.workflow.message_history.messages:
                if msg.id <= last_bubble_msg_id:
                    continue
                self.insert_bubble(msg)

            self.top_bar.load()

            # if last bubble is code then start timer
            if len(self.chat_bubbles) > 0:
                last_container = self.chat_bubbles[-1]
                auto_run_secs = False
                if last_container.bubble.role == 'code':
                    auto_run_secs = self.main.system.config.dict.get('system.auto_run_code', False)
                    if auto_run_secs:
                        last_container.btn_countdown.start_timer(secs=auto_run_secs)
                elif last_container.bubble.role == 'tool':  # todo clean
                    msg_tool_config = json.loads(last_container.bubble.text)
                    tool_id = msg_tool_config.get('tool_id', None)
                    tool_name = self.main.system.tools.tool_id_names.get(tool_id, None)
                    if tool_name:
                        tool_config = self.main.system.tools.tools.get(tool_name, None)
                        auto_run_secs = tool_config.get('auto_run', False)
                        if auto_run_secs:
                            last_container.btn_countdown.start_timer(secs=auto_run_secs)

            # Re-enable updates
            self.setUpdatesEnabled(True)
            # restore scroll position
            scroll_bar.setValue(scroll_pos)

            # Update layout
            self.chat_scroll_layout.update()
            self.updateGeometry()

            self.waiting_for_bar.load()

    def clear_bubbles(self):
        with self.workflow.message_history.thread_lock:
            while len(self.chat_bubbles) > 0:
                bubble_container = self.chat_bubbles.pop()
                self.chat_scroll_layout.removeWidget(bubble_container)
                bubble_container.hide()  # can't use deleteLater() todo

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
                else:
                    is_generating = self.workflow.responding
                    if is_generating:
                        scroll_bar = self.scroll_area.verticalScrollBar()
                        is_at_bottom = scroll_bar.value() >= scroll_bar.maximum() - 5
                        if not is_at_bottom:
                            self.decoupled_scroll = True
                        else:
                            self.decoupled_scroll = False

            if event.type() == QEvent.KeyRelease:
                if event.key() == Qt.Key_Control:
                    # self.update_text_size()

                    return True  # Stop further propagation of the wheel event
        except Exception as e:
            print(e)

        return super().eventFilter(watched, event)

    # def temp_zoom_in(self):
    #     if not self.temp_text_size:
    #         conf = self.main.system.config.dict
    #         self.temp_text_size = conf.get('display.text_size', 15)
    #     if self.temp_text_size >= 50:
    #         return
    #     self.temp_text_size += 1
    #     # self.main.page_settings.update_config('display.text_size', self.temp_text_size)
    #     # self.refresh()  # todo instead of reloading bubbles just reapply style
    #     # self.setFocus()
    #
    # def temp_zoom_out(self):
    #     if not self.temp_text_size:
    #         conf = self.main.system.config.dict
    #         self.temp_text_size = conf.get('display.text_size', 15)
    #     if self.temp_text_size <= 7:
    #         return
    #     self.temp_text_size -= 1
    #     # self.main.page_settings.update_config('display.text_size', self.temp_text_size)
    #     # self.refresh()  # todo instead of reloading bubbles just reapply style
    #     # self.setFocus()

    # def update_text_size(self):
    #     # Call this method to update the configuration once Ctrl is released
    #     if self.temp_text_size is None:
    #         return
    #     # self.main.page_settings.update_config('display.text_size', self.temp_text_size)  # todo
    #     self.temp_text_size = None

    def installEventFilterRecursively(self, widget):
        widget.installEventFilter(self)
        for child in widget.children():
            if isinstance(child, QWidget):
                self.installEventFilterRecursively(child)

    class ChatWorkflowSettings(WorkflowSettings):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent

        def save_config(self):
            json_config_dict = self.get_config()
            json_config = json.dumps(json_config_dict)
            context_id = self.parent.workflow.id
            try:
                sql.execute("UPDATE contexts SET config = ? WHERE id = ?", (json_config, context_id,))
            except sqlite3.IntegrityError as e:
                display_messagebox(
                    icon=QMessageBox.Warning,
                    title='Error',
                    text='Name already exists',
                )

            self.load_config(json_config)
            self.member_config_widget.load()
            self.parent.load(also_config=False)
            self.parent.workflow_settings.load_async_groups()
            for m in self.parent.workflow_settings.members_in_view.values():
                m.refresh_avatar()
            if not self.compact_mode:
                self.parent.workflow.load()
                self.member_list.load()
                self.refresh_member_highlights()

    class Top_Bar(QWidget):
        def __init__(self, parent):
            super().__init__(parent)

            self.parent = parent
            self.setMouseTracking(True)

            self.settings_layout = CVBoxLayout(self)

            self.input_container = QWidget()
            self.input_container.setFixedHeight(44)
            self.topbar_layout = CHBoxLayout(self.input_container)
            self.topbar_layout.setContentsMargins(6, 0, 0, 0)

            self.settings_layout.addWidget(self.input_container)

            self.profile_pic_label = QLabel(self)
            self.profile_pic_label.setFixedSize(44, 44)

            self.topbar_layout.addWidget(self.profile_pic_label)
            # connect profile label click to method 'open'
            self.profile_pic_label.mousePressEvent = self.agent_name_clicked

            self.agent_name_label = QLabel(self)

            self.lbl_font = self.agent_name_label.font()
            self.lbl_font.setPointSize(15)
            self.agent_name_label.setFont(self.lbl_font)
            self.agent_name_label.mousePressEvent = self.agent_name_clicked
            self.agent_name_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

            self.topbar_layout.addWidget(self.agent_name_label)

            self.title_label = QLineEdit(self)
            self.small_font = self.title_label.font()
            self.small_font.setPointSize(10)
            self.title_label.setFont(self.small_font)
            text_color = self.parent.main.system.config.dict.get('display.text_color', '#c4c4c4')
            self.title_label.setStyleSheet(f"QLineEdit {{ color: {apply_alpha_to_hex(text_color, 0.90)}; background-color: transparent; }}"
                                           f"QLineEdit:hover {{ color: {text_color}; }}")
            self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.title_label.textChanged.connect(self.title_edited)

            self.topbar_layout.addWidget(self.title_label)

            self.button_container = QWidget()
            self.button_layout = QHBoxLayout(self.button_container)
            self.button_layout.setSpacing(5)
            # self.button_layout.setContentsMargins(0, 0, 20, 0)

            # Create buttons
            self.btn_prev_context = IconButton(parent=self, icon_path=':/resources/icon-left-arrow.png')
            self.btn_next_context = IconButton(parent=self, icon_path=':/resources/icon-right-arrow.png')

            self.btn_prev_context.clicked.connect(self.previous_context)
            self.btn_next_context.clicked.connect(self.next_context)

            self.btn_info = QPushButton()
            self.btn_info.setText('i')
            self.btn_info.setFixedSize(25, 25)
            self.btn_info.clicked.connect(self.showContextInfo)

            self.button_layout.addWidget(self.btn_prev_context)
            self.button_layout.addWidget(self.btn_next_context)
            self.button_layout.addWidget(self.btn_info)

            # Add the container to the top bar layout
            self.topbar_layout.addWidget(self.button_container)

            self.button_container.hide()

        def load(self):
            try:
                self.agent_name_label.setText(self.parent.workflow.chat_name)
                with block_signals(self.title_label):
                    self.title_label.setText(self.parent.workflow.chat_title)
                    self.title_label.setCursorPosition(0)

                member_paths = get_avatar_paths_from_config(self.parent.workflow.config)
                member_pixmap = path_to_pixmap(member_paths, diameter=35)
                self.profile_pic_label.setPixmap(member_pixmap)
            except Exception as e:
                print(e)
                raise e

        def title_edited(self, text):
            sql.execute(f"""
                UPDATE contexts
                SET name = ?
                WHERE id = ?
            """, (text, self.parent.workflow.id,))
            self.parent.workflow.chat_title = text

        def showContextInfo(self):
            context_id = self.parent.workflow.id
            leaf_id = self.parent.workflow.leaf_id

            display_messagebox(
                icon=QMessageBox.Warning,
                text=f"Context ID: {context_id}\nLeaf ID: {leaf_id}",
                title="Context Info",
                buttons=QMessageBox.Ok,
            )

        def previous_context(self):
            context_id = self.parent.workflow.id
            prev_context_id = sql.get_scalar(
                "SELECT id FROM contexts WHERE id < ? AND parent_id IS NULL ORDER BY id DESC LIMIT 1;", (context_id,))
            if prev_context_id:
                self.parent.goto_context(prev_context_id)
                self.parent.load()
                self.btn_next_context.setEnabled(True)
            else:
                self.btn_prev_context.setEnabled(False)

        def next_context(self):
            context_id = self.parent.workflow.id
            next_context_id = sql.get_scalar(
                "SELECT id FROM contexts WHERE id > ? AND parent_id IS NULL ORDER BY id LIMIT 1;", (context_id,))
            if next_context_id:
                self.parent.goto_context(next_context_id)
                self.parent.load()
                self.btn_prev_context.setEnabled(True)
            else:
                self.btn_next_context.setEnabled(False)

        def enterEvent(self, event):
            self.button_container.show()

        def leaveEvent(self, event):
            self.button_container.hide()

        def agent_name_clicked(self, event):
            if not self.parent.workflow_settings.isVisible():
                self.parent.workflow_settings.show()
                self.parent.workflow_settings.load()
            else:
                self.parent.workflow_settings.hide()

    class WaitingForBar(QWidget):
        def __init__(self, parent, **kwargs):
            super().__init__(parent)
            self.parent = parent
            self.layout = CHBoxLayout(self)
            self.layout.setContentsMargins(0, 5, 0, 0)
            self.member_id = None
            self.member_name_label = None

        def load(self):
            next_member = self.parent.workflow.next_expected_member()
            if not next_member:
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

    class AttachmentBar(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.parent = parent
            self.layout = CVBoxLayout(self)

            self.attachments = []  # A list of filepaths
            self.hide()

        def add_attachments(self, paths):
            if not isinstance(paths, list):
                paths = [paths]

            # # remove last stretch
            # self.layout.takeAt(self.layout.count() - 1)

            for filepath in paths:
                attachment = self.Attachment(self, filepath)
                self.attachments.append(attachment)
                self.layout.addWidget(attachment)

            # self.layout.addStretch(1)

            # self.load_layout()
            self.show()

        def remove_attachment(self, attachment):
            self.attachments.remove(attachment)
            attachment.deleteLater()
            # self.load_layout()

        class Attachment(QWidget):
            def __init__(self, parent, filepath):
                super().__init__(parent)
                self.parent = parent

                self.filepath = filepath
                self.filename = os.path.basename(filepath)

                self.layout = CHBoxLayout(self)

                self.icon_label = QLabel()
                self.text_label = QLabel()
                self.text_label.setText(self.filename)

                # If is any image type
                if self.filename.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp')):
                    # show image in the qlabel
                    # big_thumbnail_pixmap = QPixmap(filepath).scaled(200, 200, Qt.KeepAspectRatio)
                    thumbnail_pixmap = QPixmap(filepath).scaled(16, 16, Qt.KeepAspectRatio)
                    self.icon_label.setPixmap(thumbnail_pixmap)

                else:
                    # show file icon
                    icon_provider = QFileIconProvider()
                    icon = icon_provider.icon(QFileInfo(filepath))
                    self.icon_label.setPixmap(icon.pixmap(16, 16))

                self.layout.addWidget(self.icon_label)
                self.layout.addWidget(self.text_label)

                remove_button = IconButton(parent=self, icon_path=':/resources/close.png')
                remove_button.clicked.connect(self.on_delete_click)

                self.layout.addWidget(remove_button)
                self.layout.addStretch(1)

            def update_widget(self):
                icon_provider = QFileIconProvider()
                icon = icon_provider.icon(QFileInfo(self.filepath))
                if icon is None or not isinstance(icon, QIcon):
                    icon = QIcon()  # Fallback to a default QIcon if no valid icon is found
                self.icon_label.setPixmap(icon.pixmap(16, 16))

            def on_delete_click(self):
                self.parent.remove_attachment(self)

    def on_send_message(self):
        if self.workflow.responding:
            self.workflow.behaviour.stop()
        else:
            self.ensure_visible()
            next_expected_member = self.workflow.next_expected_member()
            if not next_expected_member:
                return

            next_expected_member_type = next_expected_member.config.get('_TYPE', 'agent')
            as_member_id = next_expected_member.member_id if next_expected_member_type == 'user' else 1
            self.send_message(self.main.message_text.toPlainText(), clear_input=True, as_member_id=as_member_id)

    def ensure_visible(self):
        # make sure chat page button is shown
        stacked_widget = self.main.main_menu.content
        index = stacked_widget.indexOf(self)
        current_index = stacked_widget.currentIndex()
        if index != current_index:
            self.main.main_menu.settings_sidebar.page_buttons['Chat'].click()
            self.main.main_menu.settings_sidebar.page_buttons['Chat'].setChecked(True)

    # on send_msg, if last msg alt_turn is same as current, then it's same run
    def send_message(self, message, role='user', as_member_id=1, clear_input=False):
        # check if threadpool is active
        if self.threadpool.activeThreadCount() > 0:
            return

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

        self.workflow.message_history.load_branches()  # todo - figure out a nicer way to load this only when needed
        self.refresh()
        # QTimer.singleShot(5, partial(self.after_send_message, as_member_id))
        self.after_send_message(as_member_id)

    def after_send_message(self, as_member_id):
        QTimer.singleShot(5, self.scroll_to_end)
        self.run_workflow(as_member_id)
        self.try_generate_title()

    def run_workflow(self, from_member_id=None):
        self.main.send_button.update_icon(is_generating=True)
        self.refresh_waiting_bar(set_visibility=False)
        self.workflow_settings.refresh_member_highlights()
        runnable = self.RespondingRunnable(self, from_member_id)
        self.threadpool.start(runnable)

    class RespondingRunnable(QRunnable):
        def __init__(self, parent, from_member_id=None):
            super().__init__()
            self.main = parent.main
            self.page_chat = parent
            self.from_member_id = from_member_id

        def run(self):
            try:
                asyncio.run(self.page_chat.workflow.behaviour.start(self.from_member_id))
                self.main.finished_signal.emit()
            except Exception as e:
                if os.environ.get('OPENAI_API_KEY', False):  # todo this will clash with the new system
                    raise e  # re-raise the exception for debugging
                self.main.error_occurred.emit(str(e))

    @Slot(str)
    def on_error_occurred(self, error):
        with self.workflow.message_history.thread_lock:
            self.last_member_bubbles.clear()
        self.workflow.responding = False
        self.main.send_button.update_icon(is_generating=False)
        self.decoupled_scroll = False
        self.workflow_settings.refresh_member_highlights()
        self.refresh_waiting_bar(set_visibility=True)

        display_messagebox(
            icon=QMessageBox.Critical,
            text=error,
            title="Response Error",
            buttons=QMessageBox.Ok
        )

    @Slot()
    def on_receive_finished(self):
        with self.workflow.message_history.thread_lock:
            self.last_member_bubbles.clear()
        self.workflow.responding = False
        self.main.send_button.update_icon(is_generating=False)
        self.decoupled_scroll = False

        self.refresh()
        self.workflow_settings.refresh_member_highlights()
        self.refresh_waiting_bar(set_visibility=True)

    def try_generate_title(self):
        current_title = self.workflow.chat_title
        if current_title != '':
            return

        system_config = self.main.system.config.dict
        auto_title = system_config.get('system.auto_title', True)

        if not auto_title:
            return
        if not self.workflow.message_history.count(incl_roles=('user',)) == 1:
            return

        title_runnable = self.AutoTitleRunnable(self)
        self.threadpool.start(title_runnable)

    class AutoTitleRunnable(QRunnable):
        def __init__(self, parent):
            super().__init__()
            self.page_chat = parent
            self.workflow = self.page_chat.workflow

        def run(self):
            from src.system.base import manager
            user_msg = self.workflow.message_history.last(incl_roles=('user',))

            conf = self.page_chat.main.system.config.dict
            model_name = conf.get('system.auto_title_model', 'mistral/mistral-large-latest')
            model_obj = convert_model_json_to_obj(model_name)

            prompt = conf.get('system.auto_title_prompt',
                              'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}')
            prompt = prompt.format(user_msg=user_msg['content'])  # todo

            try:
                title = manager.providers.get_scalar(prompt, single_line=True, model_obj=model_obj)
                title = title.replace('\n', ' ').strip("'").strip('"')
                self.page_chat.main.title_update_signal.emit(title)
            except Exception as e:
                e_str = f'Auto title response error, check the model in System settings:\n\n{str(e)}'
                self.page_chat.main.error_occurred.emit(e_str)

    @Slot(str)
    def on_title_update(self, title):
        with block_signals(self.top_bar.title_label):
            self.top_bar.title_label.setText(title)
            self.top_bar.title_label.setCursorPosition(0)
        self.top_bar.title_edited(title)

    def insert_bubble(self, message=None):
        msg_container = MessageContainer(self, message=message)
        index = len(self.chat_bubbles)
        self.chat_bubbles.insert(index, msg_container)
        self.chat_scroll_layout.insertWidget(index, msg_container)

        return msg_container

    @Slot(str, int, str)
    def new_sentence(self, role, member_id, sentence):
        with self.workflow.message_history.thread_lock:
            if (role, member_id) not in self.last_member_bubbles:
                msg = Message(msg_id=-1, role=role, content=sentence, member_id=member_id)
                self.insert_bubble(msg)
                self.last_member_bubbles[(role, member_id)] = self.chat_bubbles[-1]
            else:
                last_member_bubble = self.last_member_bubbles[(role, member_id)]
                last_member_bubble.bubble.append_text(sentence)

            if not self.decoupled_scroll:
                QTimer.singleShot(5, self.scroll_to_end)

    def delete_messages_since(self, msg_id):
        # DELETE ALL CHAT BUBBLES >= msg_id
        with self.workflow.message_history.thread_lock:
            while self.chat_bubbles:
                bubble_cont = self.chat_bubbles.pop()
                bubble_msg_id = bubble_cont.bubble.msg_id
                self.chat_scroll_layout.removeWidget(bubble_cont)
                bubble_cont.hide()  # .deleteLater()
                if bubble_msg_id == msg_id:
                    break

            index = next((i for i, msg in enumerate(self.workflow.message_history.messages) if msg.id == msg_id), -1)

            if index <= len(self.workflow.message_history.messages) - 1:
                self.workflow.message_history.messages[:] = self.workflow.message_history.messages[:index]

    def scroll_to_end(self):
        QApplication.processEvents()  # Process GUI events to update content size
        scrollbar = self.main.page_chat.scroll_area.verticalScrollBar()

        # Create a QPropertyAnimation
        self.scroll_animation = QPropertyAnimation(scrollbar, b"value")
        self.scroll_animation.setDuration(200)  # Set the duration of the animation (in milliseconds)
        self.scroll_animation.setStartValue(scrollbar.value())
        self.scroll_animation.setEndValue(scrollbar.maximum())
        self.scroll_animation.setEasingCurve(QEasingCurve.InOutQuad)  # Set the easing curve for smooth animation
        # connect on finished
        # scroll_animation.finished.connect(self.on_scroll_animation_finished)

        # # Start the animation
        self.scroll_animation.start()

        # if not self.running_animation:
        #     self.running_animation = scroll_animation
        #     self.running_animation.start()
        # else:
        #     self.animation_queue.put(scroll_animation)
        #
        # # # # if animation is running, add to self.animation_queue (queue.Queue)
        # # # if self.running_animation.state() != QPropertyAnimation.Running:
        # #
        # #

        # # QApplication.processEvents()  # process GUI events to update content size todo?
        # # scrollbar = self.main.page_chat.scroll_area.verticalScrollBar()
        # # scrollbar.setValue(scrollbar.maximum())
        # # print('SCROLL TO END ----------------------------------------')
        # #
        # # # # raise NotImplementedError()
        # # # scrollbar = self.main.page_chat.scroll_area.verticalScrollBar()
        # # # current_value = scrollbar.value()
        # # # max_value = scrollbar.maximum()
        # # #
        # # # # Set up the animation for smooth scrolling
        # # # duration = 500
        # # # animation = QPropertyAnimation(scrollbar, b"value")
        # # # animation.setDuration(duration)  # Duration of the animation in milliseconds
        # # # animation.setStartValue(current_value)  # Start at the current scrollbar position
        # # # animation.setEndValue(max_value)  # End at the maximum value of the scrollbar
        # # # animation.setEasingCurve(QEasingCurve.OutQuad)  # Use a quadratic easing out curve for a smooth effect
        # # #
        # # # # Start the animation
        # # # animation.start(QPropertyAnimation.DeleteWhenStopped)  # Ensure the animation object is deleted when finished

    def on_scroll_animation_finished(self):
        # self.running_animation = None
        if not self.animation_queue.empty():
            next_animation = self.animation_queue.get()
            next_animation.start()
        else:
            self.running_animation = None

    def new_context(self, copy_context_id=None, entity_id=None):
        if copy_context_id:
            config = json.loads(
                sql.get_scalar("SELECT config FROM contexts WHERE id = ?", (copy_context_id,))
            )
            sql.execute("""
                INSERT INTO contexts
                    (config)
                SELECT
                    config
                FROM contexts
                WHERE id = ?""", (copy_context_id,))

        elif entity_id is not None:
            config = json.loads(
                sql.get_scalar("SELECT config FROM entities WHERE id = ?",
                               (entity_id,))
            )
            entity_type = config.get('_TYPE', 'agent')
            if entity_type == 'workflow':
                sql.execute("""
                    INSERT INTO contexts
                        (config)
                    SELECT
                        config
                    FROM entities
                    WHERE id = ?""", (entity_id,))
            else:
                wf_config = merge_config_into_workflow_config(config, entity_id)
                sql.execute("""
                    INSERT INTO contexts
                        (config)
                    VALUES (?)""", (json.dumps(wf_config),))
        else:
            raise NotImplementedError()

        context_id = sql.get_scalar("SELECT MAX(id) FROM contexts")
        # Insert welcome messages
        member_id, preload_msgs = self.get_preload_messages(config)
        for msg_dict in preload_msgs:
            role, content, typ = msg_dict.values()
            m_id = 1 if role == 'user' else member_id
            if typ == 'Welcome':
                role = 'welcome'
            sql.execute("""
                INSERT INTO contexts_messages
                    (context_id, member_id, role, msg, embedding_id, log)
                VALUES
                    (?, ?, ?, ?, ?, ?)""",
                (context_id, m_id, role, content, None, ''))

        context_id = sql.get_scalar("SELECT MAX(id) FROM contexts")
        self.goto_context(context_id)
        self.load()

    def get_preload_messages(self, config):
        member_type = config.get('_TYPE', 'agent')
        if member_type == 'workflow':
            wf_members = config.get('members', [])
            agent_members = [member_data for member_data in wf_members if member_data.get('config', {}).get('_TYPE', 'agent') == 'agent']
            if len(agent_members) == 1:
                agent_config = agent_members[0].get('config', {})
                preload_msgs = agent_config.get('chat.preload.data', '[]')
                member_id = agent_members[0]['id']
                return member_id, json.loads(preload_msgs)
            else:
                return None, []
        elif member_type == 'agent':
            agent_config = config.get('config', {})
            preload_msgs = agent_config.get('chat.preload.data', '[]')
            member_id = 2
            return member_id, json.loads(preload_msgs)
        else:
            return None, []

    def toggle_hidden_messages(self, state):
        self.show_hidden_messages = state
        self.load()

    def refresh_waiting_bar(self, set_visibility=None):
        """Optionally use set_visibility to show or hide, while respecting the system config"""
        workflow_is_multi_member = self.workflow.count_members() > 1
        show_waiting_bar_when = self.main.system.config.dict.get('display.show_waiting_bar', 'In Group')
        show_waiting_bar = ((show_waiting_bar_when == 'In Group' and workflow_is_multi_member)
                            or show_waiting_bar_when == 'Always')
        if show_waiting_bar and set_visibility is not None:
            show_waiting_bar = set_visibility
        self.waiting_for_bar.setVisible(show_waiting_bar)

    def goto_context(self, context_id=None):
        from src.members.workflow import Workflow
        self.main.page_chat.workflow = Workflow(main=self.main, context_id=context_id)
