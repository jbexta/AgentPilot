
import os
from PySide6.QtWidgets import *
from PySide6.QtCore import QThreadPool, QEvent, QTimer, QRunnable, Slot, QPoint
from PySide6.QtGui import Qt, QCursor

from agentpilot.utils.helpers import path_to_pixmap, display_messagebox, block_signals
from agentpilot.utils import sql, resources_rc
from agentpilot.utils.apis import llm

from agentpilot.context.messages import Message

import logging

from agentpilot.gui.components.group_settings import GroupSettings
from agentpilot.gui.components.bubbles import MessageContainer
from agentpilot.gui.style import TEXT_COLOR
from agentpilot.gui.widgets.base import IconButton
from agentpilot.gui.components.config import CHBoxLayout, CVBoxLayout


class Page_Chat(QWidget):
    def __init__(self, main):
        super().__init__(parent=main)
        from agentpilot.context.base import Workflow

        self.main = main
        self.workflow = Workflow(main=self.main)

        # self.temp_thread_lock = threading.Lock()
        self.threadpool = QThreadPool()
        self.chat_bubbles = []
        self.last_member_msgs = {}

        # Overall layout for the page
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # TopBar pp
        self.topbar = self.Top_Bar(self)
        self.layout.addWidget(self.topbar)

        # Scroll area for the chat
        self.scroll_area = QScrollArea(self)
        self.chat = QWidget(self.scroll_area)
        self.chat_scroll_layout = QVBoxLayout(self.chat)
        # self.chat_scroll_layout.setSpacing(0)
        self.chat_scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_scroll_layout.addStretch(1)

        self.scroll_area.setWidget(self.chat)
        self.scroll_area.setWidgetResizable(True)

        self.layout.addWidget(self.scroll_area)
        # self.layout.addStretch(1)

        self.installEventFilterRecursively(self)
        self.temp_text_size = None
        self.decoupled_scroll = False

    def load(self):
        logging.debug('Loading chat page')
        self.clear_bubbles()
        self.workflow.load()
        self.refresh()

    def load_context(self):
        from agentpilot.context.base import Workflow
        logging.debug('Loading chat page context')
        workflow_id = self.workflow.id if self.workflow else None
        self.workflow = Workflow(main=self.main, context_id=workflow_id)

    # def reload(self):
    #     # text_cursors = self.get_text_cursors()
    #     self.refresh()
    #     # self.apply_text_cursors(text_cursors)

    def refresh(self):
        logging.debug('Refreshing chat page')
        with self.workflow.message_history.thread_lock:
            # with self.temp_thread_lock:
            # iterate chat_bubbles backwards and remove any that have id = -1

            for i in range(len(self.chat_bubbles) - 1, -1, -1):
                if self.chat_bubbles[i].bubble.msg_id == -1:
                    bubble_container = self.chat_bubbles.pop(i)
                    self.chat_scroll_layout.removeWidget(bubble_container)
                    bubble_container.hide()  # deleteLater()

            last_container = self.chat_bubbles[-1] if self.chat_bubbles else None
            last_bubble_msg_id = last_container.bubble.msg_id if last_container else 0

            # get scroll position
            scroll_bar = self.scroll_area.verticalScrollBar()

            scroll_pos = scroll_bar.value()

            # self.context.message_history.load()
            for msg in self.workflow.message_history.messages:
                if msg.id <= last_bubble_msg_id:
                    continue
                self.insert_bubble(msg)

            # load the top bar
            self.topbar.load()

            # if last bubble is code then start timer
            logging.debug('Trying to start code timer')
            if len(self.chat_bubbles) > 0:
                last_bubble = self.chat_bubbles[-1].bubble
                if last_bubble.role == 'code':
                    last_bubble.start_timer()

            # restore scroll position
            scroll_bar.setValue(scroll_pos)

            # set focus to message input
            self.main.message_text.setFocus()

    def clear_bubbles(self):
        logging.debug('Clearing chat bubbles')
        with self.workflow.message_history.thread_lock:
            while len(self.chat_bubbles) > 0:
                bubble_container = self.chat_bubbles.pop()
                self.chat_scroll_layout.removeWidget(bubble_container)
                bubble_container.hide()  # .deleteLater()

    # def get_text_cursors(self):
    #     text_cursors = {}
    #     for cont in self.chat_bubbles:
    #         bubble = cont.bubble
    #         bubble_cursor = bubble.textCursor()
    #         if not bubble_cursor.hasSelection():
    #             continue
    #         text_cursors[bubble.msg_id] = bubble_cursor
    #     return text_cursors
    #
    # def apply_text_cursors(self, text_cursors):
    #     if not text_cursors:
    #         return
    #     for cont in self.chat_bubbles:
    #         bubble = cont.bubble
    #         if bubble.msg_id in text_cursors:
    #             bubble.setTextCursor(text_cursors[bubble.msg_id])
    ##############################

    # def load(self):
    #     # store existing textcursors for each textarea
    #     textcursors = {}
    #     for cont in self.chat_bubbles:
    #         bubble = cont.bubble
    #         bubble_cursor = bubble.textCursor()
    #         if not bubble_cursor.hasSelection():
    #             continue
    #         textcursors[bubble.msg_id] = bubble_cursor
    #
    #     # self.clear_bubbles()
    #     while self.chat_bubbles:
    #         bubble = self.chat_bubbles.pop()
    #         self.chat_scroll_layout.removeWidget(bubble)
    #         bubble.deleteLater()
    #     self.reload(textcursors=textcursors)

    # def reload(self, textcursors=None):
    #     self.context.load()
    #
    #     # get scroll position
    #     scroll_bar = self.scroll_area.verticalScrollBar()
    #     scroll_pos = scroll_bar.value()
    #
    #     last_container = self.chat_bubbles[-1] if self.chat_bubbles else None
    #     last_bubble_msg_id = last_container.bubble.msg_id if last_container else 0
    #     messages = self.context.message_history.messages
    #     for msg in messages:
    #         if msg.id <= last_bubble_msg_id:
    #             continue
    #         self.insert_bubble(msg)
    #
    #     if textcursors:
    #         for cont in self.chat_bubbles:
    #             bubble = cont.bubble
    #             if bubble.msg_id in textcursors:
    #                 bubble.setTextCursor(textcursors[bubble.msg_id])
    #
    #     self.topbar.load()
    #
    #     # if last bubble is code then start timer
    #     if self.chat_bubbles:
    #         last_bubble = self.chat_bubbles[-1].bubble
    #         if last_bubble.role == 'code':
    #             last_bubble.start_timer()
    #
    #     # restore scroll position
    #     scroll_bar.setValue(scroll_pos)
    #     # scroll_bar.setValue(scroll_bar.maximum())
    #     # if not self.decoupled_scroll:
    #     #     self.scroll_to_end()

    def eventFilter(self, watched, event):
        try:
            if event.type() == QEvent.Wheel:
                if event.modifiers() & Qt.ControlModifier:
                    delta = event.angleDelta().y()

                    if delta > 0:
                        self.temp_zoom_in()
                    else:
                        self.temp_zoom_out()

                    return True  # Stop further propagation of the wheel event
                else:
                    is_generating = self.workflow.responding
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
        except Exception as e:
            print(e)

        return super().eventFilter(watched, event)

    def temp_zoom_in(self):
        if not self.temp_text_size:
            conf = self.main.system.config.dict
            self.temp_text_size = conf.get('display.text_size', 15)
        if self.temp_text_size >= 50:
            return
        self.temp_text_size += 1
        # self.main.page_settings.update_config('display.text_size', self.temp_text_size)
        # self.refresh()  # todo instead of reloading bubbles just reapply style
        # self.setFocus()

    def temp_zoom_out(self):
        if not self.temp_text_size:
            conf = self.main.system.config.dict
            self.temp_text_size = conf.get('display.text_size', 15)
        if self.temp_text_size <= 7:
            return
        self.temp_text_size -= 1
        # self.main.page_settings.update_config('display.text_size', self.temp_text_size)
        # self.refresh()  # todo instead of reloading bubbles just reapply style
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
    class Top_Bar(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            logging.debug('Initializing top bar')

            self.parent = parent
            self.setMouseTracking(True)

            self.settings_layout = CVBoxLayout(self)

            self.input_container = QWidget()
            self.input_container.setFixedHeight(44)
            self.topbar_layout = CHBoxLayout(self.input_container)
            self.topbar_layout.setContentsMargins(6, 0, 0, 0)

            self.group_settings = GroupSettings(self)
            self.group_settings.hide()

            self.settings_layout.addWidget(self.input_container)
            self.settings_layout.addWidget(self.group_settings)
            # self.settings_layout.addStretch(1)

            self.profile_pic_label = QLabel(self)
            self.profile_pic_label.setFixedSize(44, 44)

            self.topbar_layout.addWidget(self.profile_pic_label)
            # connect profile label click to method 'open'
            self.profile_pic_label.mousePressEvent = self.agent_name_clicked  # todo reimplement

            self.agent_name_label = QLabel(self)

            # print('#421')
            self.lbl_font = self.agent_name_label.font()
            self.lbl_font.setPointSize(15)
            self.agent_name_label.setFont(self.lbl_font)
            # self.agent_name_label.setStyleSheet(f"QLabel {{ color: #b3{TEXT_COLOR.replace('#', '')}; }}"
            #                                     f"QLabel:hover {{ color: #cc{TEXT_COLOR.replace('#', '')}; }}")
            self.agent_name_label.mousePressEvent = self.agent_name_clicked  # todo reimplement
            self.agent_name_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

            self.topbar_layout.addWidget(self.agent_name_label)

            self.title_label = QLineEdit(self)
            # print('#420')
            self.small_font = self.title_label.font()
            self.small_font.setPointSize(10)
            self.title_label.setFont(self.small_font)
            self.title_label.setStyleSheet(f"QLineEdit {{ color: #E6{TEXT_COLOR.replace('#', '')}; background-color: transparent; }}"
                                           f"QLineEdit:hover {{ color: {TEXT_COLOR}; }}")
            self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.title_label.textChanged.connect(self.title_edited)

            self.topbar_layout.addWidget(self.title_label)

            # self.topbar_layout.addStretch(1)

            self.button_container = QWidget()
            self.button_layout = QHBoxLayout(self.button_container)
            self.button_layout.setSpacing(5)
            self.button_layout.setContentsMargins(0, 0, 20, 0)

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
            logging.debug('Loading top bar')
            try:  # temp todo
                self.group_settings.load()
                self.agent_name_label.setText(self.parent.workflow.chat_name)
                with block_signals(self.title_label):
                    self.title_label.setText(self.parent.workflow.chat_title)
                    self.title_label.setCursorPosition(0)

                member_configs = [member.config for _, member in self.parent.workflow.members.items()]
                member_avatar_paths = [config.get('general.avatar_path', '') for config in member_configs]

                circular_pixmap = path_to_pixmap(member_avatar_paths, diameter=35)
                self.profile_pic_label.setPixmap(circular_pixmap)
            except Exception as e:
                print(e)
                raise e

        def title_edited(self, text):
            logging.debug('Top bar title edited')
            sql.execute(f"""
                UPDATE contexts
                SET summary = ?
                WHERE id = ?
            """, (text, self.parent.workflow.id,))
            self.parent.workflow.chat_title = text

        def showContextInfo(self):
            logging.debug('Showing context info')
            context_id = self.parent.workflow.id
            leaf_id = self.parent.workflow.leaf_id

            display_messagebox(
                icon=QMessageBox.Warning,
                text=f"Context ID: {context_id}\nLeaf ID: {leaf_id}",
                title="Context Info",
                buttons=QMessageBox.Ok,
            )

        def previous_context(self):
            logging.debug('Top bar previous context clicked')
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
            logging.debug('Top bar next context clicked')
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
            logging.debug('Top bar enter event')
            self.button_container.show()

        def leaveEvent(self, event):
            logging.debug('Top bar leave event')
            self.button_container.hide()

        def agent_name_clicked(self, event):
            logging.debug('Top bar agent name clicked')
            if not self.group_settings.isVisible():
                self.group_settings.show()
                self.group_settings.load()
            else:
                self.group_settings.hide()

    def on_button_click(self):
        if self.workflow.responding:
            self.workflow.behaviour.stop()
        else:
            self.send_message(self.main.message_text.toPlainText(), clear_input=True)

    def send_message(self, message, role='user', clear_input=False):
        # check if threadpool is active
        if self.threadpool.activeThreadCount() > 0:
            return

        new_msg = self.workflow.save_message(role, message)
        self.last_member_msgs.clear()

        if not new_msg:
            return

        self.main.send_button.update_icon(is_generating=True)

        if clear_input:
            self.main.message_text.clear()
            self.main.message_text.setFixedHeight(51)
            self.main.send_button.setFixedHeight(51)

        # if role == 'user':
        #     # msg = Message(msg_id=-1, role='user', content=new_msg.content)
        #     self.insert_bubble(new_msg)

        self.workflow.message_history.load_branches()  # todo - figure out a nicer way to load this only when needed
        self.refresh()
        QTimer.singleShot(5, self.after_send_message)

    def after_send_message(self):
        self.scroll_to_end()
        runnable = self.RespondingRunnable(self)
        self.threadpool.start(runnable)

    class RespondingRunnable(QRunnable):
        def __init__(self, parent):
            super().__init__()
            self.main = parent.main
            self.page_chat = parent
            self.context = self.page_chat.workflow

        def run(self):
            if os.environ.get('OPENAI_API_KEY', False):
                # Bubble exceptions for development
                self.context.behaviour.start()
                self.main.finished_signal.emit()
            else:
                try:
                    self.context.behaviour.start()
                    self.main.finished_signal.emit()
                except Exception as e:
                    self.main.error_occurred.emit(str(e))

    @Slot(str)
    def on_error_occurred(self, error):
        logging.debug('Response error occurred')
        with self.workflow.message_history.thread_lock:
            self.last_member_msgs.clear()
        self.workflow.responding = False
        self.main.send_button.update_icon(is_generating=False)
        self.decoupled_scroll = False

        display_messagebox(
            icon=QMessageBox.Critical,
            text=error,
            title="Response Error",
            buttons=QMessageBox.Ok
        )

    @Slot()
    def on_receive_finished(self):
        logging.debug('Response finished')
        with self.workflow.message_history.thread_lock:
            self.last_member_msgs.clear()
        self.workflow.responding = False
        self.main.send_button.update_icon(is_generating=False)
        self.decoupled_scroll = False

        self.refresh()
        self.try_generate_title()

    def try_generate_title(self):
        current_title = self.workflow.chat_title
        if current_title != '':
            return

        logging.debug('Try generate title')
        first_config = next(iter(self.workflow.member_configs.values()))
        auto_title = first_config.get('context.auto_title', True)

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
            user_msg = self.workflow.message_history.last(incl_roles=('user',))

            conf = self.page_chat.main.system.config.dict
            model_name = conf.get('system.auto_title_model', 'gpt-3.5-turbo')
            model_obj = (model_name, self.workflow.main.system.models.to_dict()[model_name])  # todo make prettier

            prompt = conf.get('system.auto_title_prompt',
                              'Generate a brief and concise title for a chat that begins with the following message:\n\n{user_msg}')
            prompt = prompt.format(user_msg=user_msg['content'])

            try:
                title = llm.get_scalar(prompt, model_obj=model_obj)
                title = title.replace('\n', ' ').strip("'").strip('"')
                self.page_chat.main.title_update_signal.emit(title)
            except Exception as e:
                # show error message
                display_messagebox(
                    icon=QMessageBox.Warning,
                    text="Error generating title, try changing the model in settings.\n\n" + str(e),
                    title="Auto-title Error",
                    buttons=QMessageBox.Ok
                )

    @Slot(str)
    def on_title_update(self, title):
        with block_signals(self.topbar.title_label):
            self.topbar.title_label.setText(title)
        self.topbar.title_edited(title)

    def insert_bubble(self, message=None):
        logging.debug('Inserting bubble')

        msg_container = MessageContainer(self, message=message)

        if message.role == 'assistant':
            member_id = message.member_id
            if member_id:
                self.last_member_msgs[member_id] = msg_container

        index = len(self.chat_bubbles)
        self.chat_bubbles.insert(index, msg_container)
        self.chat_scroll_layout.insertWidget(index, msg_container)

        return msg_container

    @Slot(int, str)
    def new_sentence(self, member_id, sentence):
        logging.debug('New sentence')
        with self.workflow.message_history.thread_lock:
            if member_id not in self.last_member_msgs:
                # with self.temp_thread_lock:
                # msg_id = self.context.message_history.get_next_msg_id()
                msg = Message(msg_id=-1, role='assistant', content=sentence, member_id=member_id)
                self.insert_bubble(msg)
                self.last_member_msgs[member_id] = self.chat_bubbles[-1]
            else:
                last_member_bubble = self.last_member_msgs[member_id]
                last_member_bubble.bubble.append_text(sentence)

            if not self.decoupled_scroll:
                QTimer.singleShot(0, self.scroll_to_end)

    def delete_messages_since(self, msg_id):
        logging.debug('Deleting messages since')
        # DELETE ALL CHAT BUBBLES >= msg_id
        # with self.temp_thread_lock:
        with self.workflow.message_history.thread_lock:
            while self.chat_bubbles:
                bubble_cont = self.chat_bubbles.pop()
                bubble_msg_id = bubble_cont.bubble.msg_id
                self.chat_scroll_layout.removeWidget(bubble_cont)
                bubble_cont.hide()  # .deleteLater()
                if bubble_msg_id == msg_id:
                    break

            index = next((i for i, msg in enumerate(self.workflow.message_history.messages) if msg.id == msg_id), -1)

            # DELETE ALL MESSAGES >= msg_id
            if index <= len(self.workflow.message_history.messages) - 1:
                self.workflow.message_history.messages[:] = self.workflow.message_history.messages[:index]

    def scroll_to_end(self):
        logging.debug('Scrolling to end')
        QApplication.processEvents()  # process GUI events to update content size todo?
        scrollbar = self.main.page_chat.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def new_context(self, copy_context_id=None, agent_id=None):
        logging.debug('GUI new context')
        sql.execute("INSERT INTO contexts (id) VALUES (NULL)")
        context_id = sql.get_scalar("SELECT MAX(id) FROM contexts")
        if copy_context_id:
            copied_cm_id_list = sql.get_results("""
                SELECT
                    cm.id
                FROM contexts_members cm
                WHERE cm.context_id = ?
                    AND cm.del = 0
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
                    AND cm.del = 0
                ORDER BY cm.id""",
                        (context_id, copy_context_id))

            pasted_cm_id_list = sql.get_results("""
                SELECT
                    cm.id
                FROM contexts_members cm
                WHERE cm.context_id = ?
                    AND cm.del = 0
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
                cmi[2] = None if cmi[2] is None else mapped_cm_id_dict[cmi[2]]

                sql.execute("""
                    INSERT INTO contexts_members_inputs
                        (member_id, input_member_id, type)
                    VALUES
                        (?, ?, ?)""", (cmi[1], cmi[2], cmi[3]))

        elif agent_id is not None:
            sql.execute("""
                INSERT INTO contexts_members
                    (context_id, agent_id, agent_config)
                SELECT
                    ?, id, config
                FROM agents
                WHERE id = ?""", (context_id, agent_id))

        self.goto_context(context_id)
        self.main.page_chat.load()

    def goto_context(self, context_id=None):
        from agentpilot.context.base import Workflow
        self.main.page_chat.workflow = Workflow(main=self.main, context_id=context_id)